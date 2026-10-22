#include "TextureDisplacement.hpp"

#include <Eigen/Core>
#include <Eigen/Geometry>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <cassert>
#include <chrono>
#include <cmath>
#include <iterator>
#include <limits>
#include <map>
#include <memory>
#include <math.h>
#include <mutex>
#include <numeric>
#include <optional>
#include "nlohmann/json.hpp"
#include <queue>
#include <ratio>
#include <string>
#include <tuple>
#include <unordered_map>
#include <unordered_set>

#include <Eigen/Eigenvalues>

#include <tbb/blocked_range.h>
#include <tbb/parallel_for.h>
#include <tbb/parallel_sort.h>

#include <boost/log/trivial.hpp>
#include <utility>
#include <vector>

#include "AABBTreeIndirect.hpp"
#include "MeshBoolean.hpp"
#include "Model.hpp"
#include "PNGReadWrite.hpp"
#include "Point.hpp"
#include "TriangleMesh.hpp"
#include "TriangleSelector.hpp"

namespace Slic3r {

bool DecodedHeightTexture::texel_tap(const Vec2f &uv, bool tile_enabled, TextureTileMethod tile_method,
                                     TexelTap &tap) const
{
    if (empty())
        return false;

    auto repeat01 = [](float x) {
        x = std::fmod(x, 1.f);
        return x < 0.f ? x + 1.f : x;
    };
    // Standard mirrored-repeat: reflect back and forth every other unit, so tile edges always
    // line up with themselves instead of jumping from one edge of the image to the other.
    auto mirrored_repeat01 = [](float x) {
        x = std::fmod(std::abs(x), 2.f);
        return x > 1.f ? 2.f - x : x;
    };

    if (!tile_enabled && (uv.x() < 0.f || uv.x() >= 1.f || uv.y() < 0.f || uv.y() >= 1.f))
        // Outside the single, non-repeating placement entirely: no texture there, not "smeared
        // edge pixel" - clamping the *coordinate* to [0, 1] would otherwise keep returning the
        // border row/column's height forever in every direction, stretching it out to infinity.
        return false;

    float u, v;
    if (!tile_enabled) {
        u = uv.x();
        v = uv.y();
    } else if (tile_method == TextureTileMethod::MirroredRepeat) {
        u = mirrored_repeat01(uv.x());
        v = mirrored_repeat01(uv.y());
    } else {
        u = repeat01(uv.x());
        v = repeat01(uv.y());
    }

    const float fx = u * float(width);
    const float fy = v * float(height);
    const int   x0 = std::clamp(int(std::floor(fx)), 0, width - 1);
    const int   y0 = std::clamp(int(std::floor(fy)), 0, height - 1);
    // Neighbour for bilinear filtering: wrap for tiling methods, clamp at the edge otherwise (a
    // repeating neighbour would incorrectly blend against the opposite edge of the image).
    tap.x0 = x0;
    tap.y0 = y0;
    tap.x1 = tile_enabled ? (x0 + 1) % width  : std::min(x0 + 1, width - 1);
    tap.y1 = tile_enabled ? (y0 + 1) % height : std::min(y0 + 1, height - 1);
    tap.tx = fx - std::floor(fx);
    tap.ty = fy - std::floor(fy);
    return true;
}

float DecodedHeightTexture::sample(const Vec2f &uv, bool tile_enabled, TextureTileMethod tile_method) const
{
    TexelTap tap;
    if (!texel_tap(uv, tile_enabled, tile_method, tap))
        return 0.f;
    const int   x0 = tap.x0, y0 = tap.y0, x1 = tap.x1, y1 = tap.y1;
    const float tx = tap.tx, ty = tap.ty;

    auto at = [this](int x, int y) { return float(pixels[size_t(y) * size_t(width) + size_t(x)]) / 255.f; };
    const float top    = at(x0, y0) * (1.f - tx) + at(x1, y0) * tx;
    const float bottom = at(x0, y1) * (1.f - tx) + at(x1, y1) * tx;
    return top * (1.f - ty) + bottom * ty;
}

Vec3f DecodedHeightTexture::sample_color(const Vec2f &uv, bool tile_enabled, TextureTileMethod tile_method) const
{
    TexelTap tap;
    if (!has_color() || !texel_tap(uv, tile_enabled, tile_method, tap))
        return Vec3f::Zero();

    auto at = [this](int x, int y) {
        const size_t i = (size_t(y) * size_t(width) + size_t(x)) * 3;
        return Vec3f(float(rgb[i]) / 255.f, float(rgb[i + 1]) / 255.f, float(rgb[i + 2]) / 255.f);
    };
    const Vec3f top    = at(tap.x0, tap.y0) * (1.f - tap.tx) + at(tap.x1, tap.y0) * tap.tx;
    const Vec3f bottom = at(tap.x0, tap.y1) * (1.f - tap.tx) + at(tap.x1, tap.y1) * tap.tx;
    return top * (1.f - tap.ty) + bottom * tap.ty;
}

namespace {
// Decoding a PNG (zlib inflate + defilter) is real work, and image_data never changes in place
// once assigned to a layer (a new texture always gets a brand new image_data), so the decoded
// result can be cached for the lifetime of that specific image_data allocation. This matters
// because the GUI's live preview calls decode_height_texture() again on every rebuild (every
// paint stroke / parameter tweak), which would otherwise re-decode the same unchanged bytes over
// and over. Keyed by a weak_ptr (not just the raw pointer) so a freed image_data's address being
// reused by an unrelated later allocation can never alias a stale cache entry: a weak_ptr to a
// destroyed object always fails to lock, forcing a correct re-decode instead of a false hit.
struct DecodedTextureCache
{
    std::mutex mutex;
    std::unordered_map<const void *, std::pair<std::weak_ptr<const std::vector<unsigned char>>, DecodedHeightTexture>> entries;
};
DecodedTextureCache g_decoded_texture_cache;

// The smoothed copy is cached too, one per image: the thumbnail, the shaded-preview height texture, the
// colour texture, the projector texture, the UV editor's background and the preview job all ask for
// the same (image, smoothing) pair in the same frame while the Smoothing slider moves, and each of them
// blurring its own copy is what froze the UI. Keyed like the raw cache; a different smoothing value
// simply replaces the entry.
struct SmoothedTextureCache
{
    struct Entry
    {
        std::weak_ptr<const std::vector<unsigned char>> source;
        float                                           smoothing = 0.f;
        // Part of the key, not of the result: smoothing is applied *after* the panel's adjustments, so a
        // blur computed over one set of adjustments is not the blur another set would give.
        TextureAdjustments                              adjust;
        DecodedHeightTexture                            texture;
    };
    std::mutex                                   mutex;
    std::unordered_map<const void *, Entry>      entries;
};
SmoothedTextureCache g_smoothed_texture_cache;

// The adjusted copy, cached between the raw decode and the smoothed one. Needed for the same reason the
// smoothed cache is: while a slider in the image-adjustment panel moves, the thumbnail, the shaded
// preview's height and colour textures, the UV editor backdrop and the displacement preview job all ask
// for the same (image, adjustments) pair within one frame, and each of them running a full-size resample
// of its own is what would make the panel unusable on a large texture.
struct AdjustedTextureCache
{
    struct Entry
    {
        std::weak_ptr<const std::vector<unsigned char>> source;
        TextureAdjustments                              adjust;
        DecodedHeightTexture                            texture;
    };
    std::mutex                              mutex;
    std::unordered_map<const void *, Entry> entries;
};
AdjustedTextureCache g_adjusted_texture_cache;
} // namespace

namespace {
// A few passes of a separable box blur approximate a Gaussian, cheaply. `radius` is in whole texels;
// 0 is a no-op. Wraps at the edges so a tiling height map stays seamless after smoothing. Operates on
// the grayscale byte buffer in place.
//
// Each pass is a sliding window - one add and one subtract per texel - so the cost is the image size,
// not the image size times the radius. The Smoothing slider drives this on every frame it moves, for
// every consumer of the layer, and the radius goes up to 48 texels: the per-window loop this replaces
// stalled the UI for seconds on a large map. Rows (and column blocks) run in parallel. The rounding is
// the old code's exactly, so a blur gives the same bytes as before.
void smooth_height_pixels_box(std::vector<uint8_t> &pixels, int width, int height, int radius)
{
    if (radius <= 0 || width <= 0 || height <= 0 || pixels.size() != size_t(width) * size_t(height))
        return;

    const int   window = 2 * radius + 1;
    const float inv    = 1.f / float(window);
    const auto  wrap   = [](int i, int n) { return (i % n + n) % n; };
    std::vector<uint8_t> tmp(pixels.size());

    for (int pass = 0; pass < 2; ++pass) { // two passes -> smoother than a single box
        // Horizontal: a running sum per row.
        tbb::parallel_for(tbb::blocked_range<int>(0, height), [&](const tbb::blocked_range<int> &r) {
            for (int y = r.begin(); y < r.end(); ++y) {
                const uint8_t *src = pixels.data() + size_t(y) * size_t(width);
                uint8_t       *dst = tmp.data() + size_t(y) * size_t(width);
                uint32_t       sum = 0;
                for (int k = -radius; k <= radius; ++k)
                    sum += src[wrap(k, width)];
                for (int x = 0; x < width; ++x) {
                    dst[x] = uint8_t(std::lround(float(sum) * inv));
                    sum += src[wrap(x + radius + 1, width)];
                    sum -= src[wrap(x - radius, width)];
                }
            }
        });
        // Vertical: one running sum per column, advanced row by row so the reads stay row-major.
        tbb::parallel_for(tbb::blocked_range<int>(0, width, 256), [&](const tbb::blocked_range<int> &r) {
            std::vector<uint32_t> sum(size_t(r.size()), 0);
            for (int k = -radius; k <= radius; ++k) {
                const uint8_t *row = tmp.data() + size_t(wrap(k, height)) * size_t(width);
                for (int x = r.begin(); x < r.end(); ++x)
                    sum[size_t(x - r.begin())] += row[x];
            }
            for (int y = 0; y < height; ++y) {
                uint8_t       *dst = pixels.data() + size_t(y) * size_t(width);
                const uint8_t *add = tmp.data() + size_t(wrap(y + radius + 1, height)) * size_t(width);
                const uint8_t *sub = tmp.data() + size_t(wrap(y - radius, height)) * size_t(width);
                for (int x = r.begin(); x < r.end(); ++x) {
                    uint32_t &sx = sum[size_t(x - r.begin())];
                    dst[x] = uint8_t(std::lround(float(sx) * inv));
                    sx += add[x];
                    sx -= sub[x];
                }
            }
        });
    }
}

// The same blur with a *continuous* radius, which is what the Smoothing slider drives.
//
// A box blur can only work in whole texels, so mapping the slider straight onto a rounded radius
// made it move in visible jumps - and its very first step off zero was a full one-texel blur rather
// than a hint of one, which is what made the control feel like it switched on rather than ramped up.
// Blur at the next whole texel up and cross-fade the raw image back in by the fraction left over:
// below one texel that fade *is* the sub-texel kernel, and above it it turns each integer step into
// a continuous ramp.
void smooth_height_pixels(std::vector<uint8_t> &pixels, int width, int height, float radius)
{
    if (radius <= 0.f || width <= 0 || height <= 0 || pixels.size() != size_t(width) * size_t(height))
        return;

    const int   whole = std::max(1, int(std::ceil(radius)));
    const float mix   = std::clamp(radius / float(whole), 0.f, 1.f);
    const std::vector<uint8_t> raw = (mix < 0.999f) ? pixels : std::vector<uint8_t>{};
    smooth_height_pixels_box(pixels, width, height, whole);
    if (!raw.empty())
        for (size_t i = 0; i < pixels.size(); ++i)
            pixels[i] = uint8_t(std::lround(float(raw[i]) + (float(pixels[i]) - float(raw[i])) * mix));
}
} // namespace

bool height_texture_has_color(const TextureDisplacementLayer &layer)
{
    if (layer.empty())
        return false;
    {
        std::lock_guard<std::mutex> lock(g_decoded_texture_cache.mutex);
        const auto it = g_decoded_texture_cache.entries.find(layer.image_data.get());
        if (it != g_decoded_texture_cache.entries.end() && it->second.first.lock() == layer.image_data)
            return it->second.second.has_color();
    }
    // Not decoded yet. Decoding caches the raw image, so this happens once per image.
    return decode_height_texture(layer).has_color();
}

DecodedHeightTexture decode_height_texture(const TextureDisplacementLayer &layer)
{
    DecodedHeightTexture result;
    if (layer.empty())
        return result;

    // The raw (unsmoothed) decode is what gets cached, keyed by the image_data allocation - decoding
    // a PNG is the expensive part and never changes for a given image. Smoothing is applied afterwards
    // to a throwaway copy, so moving the smoothing slider never invalidates the decode cache.
    const void *key = layer.image_data.get();
    bool        have_raw = false;
    {
        std::lock_guard<std::mutex> lock(g_decoded_texture_cache.mutex);
        auto it = g_decoded_texture_cache.entries.find(key);
        if (it != g_decoded_texture_cache.entries.end() && it->second.first.lock() == layer.image_data) {
            result   = it->second.second;
            have_raw = true;
        }
    }

    if (!have_raw) {
        const png::ReadBuf rbuf{ layer.image_data->data(), layer.image_data->size() };
        if (!png::is_png(rbuf))
            // PNG only. The GUI converts any other imported format (jpg, bmp, ...) on import, so this
            // code needs no dependency on wxWidgets/libjpeg to read arbitrary user images.
            return result;

        png::ImageGreyscale img;
        if (png::decode_png(rbuf, img) && img.cols > 0 && img.rows > 0) {
            // The shipped library, and anything imported before colour was kept.
            result.width  = int(img.cols);
            result.height = int(img.rows);
            result.pixels = std::move(img.buf);
        } else {
            // A colour source: keep the colour, and take the height from its luminance. The
            // coefficients are wxImage::ConvertToGreyscale()'s, which is what the importer used to
            // apply on the way in - so a texture that used to be flattened to grey at import time
            // displaces identically now that its colour is preserved.
            // The loop below steps bytes_per_pixel per texel, which only holds at 8 bits per channel:
            // decode_colored_png() does not narrow a 16-bit image, so that would read as noise.
            png::ImageColorscale col;
            if (!png::decode_colored_png(rbuf, col) || col.cols == 0 || col.rows == 0 ||
                col.bytes_per_pixel < 3 || col.buf.size() != col.cols * col.rows * size_t(col.bytes_per_pixel))
                return result;

            const int    w   = int(col.cols);
            const int    h   = int(col.rows);
            const size_t bpp = size_t(col.bytes_per_pixel);
            result.width  = w;
            result.height = h;
            result.pixels.resize(size_t(w) * size_t(h));
            result.rgb.resize(size_t(w) * size_t(h) * 3);
            // decode_colored_png() hands its buffer back bottom-up - it is shared with the CLI's
            // plate-thumbnail loader, which expects that - while this type, and decode_png()'s
            // grayscale path above, are top-to-bottom. Reverse the rows on the way in so a colour
            // height map displaces the same way up as a grayscale one.
            for (int y = 0; y < h; ++y)
                for (int x = 0; x < w; ++x) {
                    const uint8_t *src = col.buf.data() + (size_t(h - 1 - y) * size_t(w) + size_t(x)) * bpp;
                    const size_t   dst = size_t(y) * size_t(w) + size_t(x);
                    const uint8_t  r = src[0], g = src[1], b = src[2];
                    result.rgb[dst * 3]     = r;
                    result.rgb[dst * 3 + 1] = g;
                    result.rgb[dst * 3 + 2] = b;
                    result.pixels[dst] = uint8_t(std::lround(0.299 * r + 0.587 * g + 0.114 * b));
                }
        }

        std::lock_guard<std::mutex> lock(g_decoded_texture_cache.mutex);
        // Opportunistically drop entries for image_data that no longer exists anywhere, so the
        // cache doesn't grow without bound across many add/remove-texture cycles in a long session.
        auto &entries = g_decoded_texture_cache.entries;
        for (auto it = entries.begin(); it != entries.end();)
            it = it->second.first.expired() ? entries.erase(it) : std::next(it);
        entries[key] = { std::weak_ptr<const std::vector<unsigned char>>(layer.image_data), result };
    }

    // The image-adjustment panel's live edits, on top of the decode and before the smoothing. Before,
    // because `preview_adjust` is an edit to the image while `smoothing` is a live low-pass over whatever
    // the image is - the same order the panel presents them in, and the same order a commit bakes in.
    //
    // Nothing applies here once the panel has closed: it resets preview_adjust to identity, and identity
    // is a no-op that costs one comparison.
    if (!layer.preview_adjust.identity()) {
        bool have_adjusted = false;
        {
            std::lock_guard<std::mutex> lock(g_adjusted_texture_cache.mutex);
            auto it = g_adjusted_texture_cache.entries.find(key);
            if (it != g_adjusted_texture_cache.entries.end() && it->second.adjust == layer.preview_adjust &&
                it->second.source.lock() == layer.image_data) {
                result        = it->second.texture;
                have_adjusted = true;
            }
        }
        if (!have_adjusted) {
            result = apply_texture_adjustments(result, layer.preview_adjust);
            std::lock_guard<std::mutex> lock(g_adjusted_texture_cache.mutex);
            auto &entries = g_adjusted_texture_cache.entries;
            for (auto it = entries.begin(); it != entries.end();)
                it = it->second.source.expired() ? entries.erase(it) : std::next(it);
            entries[key] = { std::weak_ptr<const std::vector<unsigned char>>(layer.image_data),
                             layer.preview_adjust, result };
        }
    }

    // Smoothing radius scales with the texture so the same slider value blurs the same *fraction* of
    // the image whatever resolution it came in at, and stays continuous in the slider - see
    // smooth_height_pixels(). The cap is a cost limit, not part of the mapping: the blur is
    // O(width * height * radius) per pass, so a large map with the slider at the top would otherwise
    // stall every preview rebuild.
    if (layer.smoothing > 0.f) {
        {
            std::lock_guard<std::mutex> lock(g_smoothed_texture_cache.mutex);
            auto it = g_smoothed_texture_cache.entries.find(key);
            if (it != g_smoothed_texture_cache.entries.end() && it->second.smoothing == layer.smoothing &&
                it->second.adjust == layer.preview_adjust && it->second.source.lock() == layer.image_data)
                return it->second.texture;
        }
        const float span   = 0.05f * float(std::min(result.width, result.height));
        const float radius = std::clamp(layer.smoothing, 0.f, 1.f) * std::min(span, 48.f);
        smooth_height_pixels(result.pixels, result.width, result.height, radius);
        // Colour gets the same blur, per channel. It is the same knob for the same reason: detail in
        // the image finer than the mesh can carry is noise either way, and low-passing it here is the
        // cheapest place to remove it - one blur of the texture, rather than a fight per triangle.
        if (result.has_color()) {
            const size_t         n = size_t(result.width) * size_t(result.height);
            std::vector<uint8_t> channel(n);
            for (int c = 0; c < 3; ++c) {
                for (size_t i = 0; i < n; ++i)
                    channel[i] = result.rgb[i * 3 + size_t(c)];
                smooth_height_pixels(channel, result.width, result.height, radius);
                for (size_t i = 0; i < n; ++i)
                    result.rgb[i * 3 + size_t(c)] = channel[i];
            }
        }
        std::lock_guard<std::mutex> lock(g_smoothed_texture_cache.mutex);
        auto &entries = g_smoothed_texture_cache.entries;
        for (auto it = entries.begin(); it != entries.end();)
            it = it->second.source.expired() ? entries.erase(it) : std::next(it);
        entries[key] = { std::weak_ptr<const std::vector<unsigned char>>(layer.image_data), layer.smoothing,
                         layer.preview_adjust, result };
    }
    return result;
}

namespace {
// Fraction of the short side that TextureAdjustments::blur == 1 blurs over, and the cost cap on it.
// Deliberately the same pair decode_height_texture() uses for the Smoothing slider - see
// adjustment_blur_radius().
constexpr float SOURCE_BLUR_SPAN   = 0.05f;
constexpr float SOURCE_BLUR_MAX_PX = 48.f;

// Radius of the unsharp mask's blurred reference, in texels. Small and only mildly resolution-dependent:
// a sharpen is meant to act on the finest detail the image holds, so its radius tracks the texel grid
// rather than the picture's size. 1024x1024 gives ~2 texels, the usual photo-editor default.
float unsharp_radius(int width, int height)
{
    return std::max(1.f, 0.002f * float(std::min(width, height)));
}

// Brightness as a *lift* toward white (or toward black) rather than an additive offset: positive b maps
// v to v + b*(1 - v), negative to v*(1 + b). Both reach the endpoint exactly at |b| == 1 while staying
// monotonic and non-clipping in between, which an additive shift does not - it drives a whole region to
// a flat 255 and, because this image is also the height map, that region bakes as flat relief rather
// than as bright relief. Keeping the curve injective keeps the detail in it.
float apply_brightness(float v, float b)
{
    return b >= 0.f ? v + b * (1.f - v) : v * (1.f + b);
}

// Contrast about the 0.5 pivot. Gain is 1/(1-c) going up (c == 1 would be an infinite-slope threshold, so
// the caller's clamp keeps it finite) and 1+c going down, reaching a flat mid-grey at c == -1.
float apply_contrast(float v, float c)
{
    const float gain = c >= 0.f ? 1.f / std::max(1e-3f, 1.f - c) : 1.f + c;
    return (v - 0.5f) * gain + 0.5f;
}

// Blur then sharpen one 8-bit channel in place. Shared by the grayscale path and by each of a colour
// image's three channels, so every channel gets the identical spatial treatment and a colour image's
// hue cannot shift just because its channels were filtered differently.
void adjust_channel_spatial(std::vector<uint8_t> &channel, int width, int height, float blur, float sharpness)
{
    if (blur > 0.f)
        smooth_height_pixels(channel, width, height, adjustment_blur_radius(blur, width, height));

    if (sharpness <= 0.f)
        return;

    // Unsharp mask: push each texel away from its local average by `amount` times the difference. The
    // blurred reference is a copy, so the sharpen reads the un-sharpened neighbourhood everywhere rather
    // than its own partly-written output.
    std::vector<uint8_t> base = channel;
    smooth_height_pixels(base, width, height, unsharp_radius(width, height));
    const float amount = 1.5f * std::clamp(sharpness, 0.f, 1.f);
    tbb::parallel_for(tbb::blocked_range<size_t>(0, channel.size()), [&](const tbb::blocked_range<size_t> &r) {
        for (size_t i = r.begin(); i < r.end(); ++i) {
            const float v = float(channel[i]) + amount * (float(channel[i]) - float(base[i]));
            channel[i]    = uint8_t(std::lround(std::clamp(v, 0.f, 255.f)));
        }
    });
}

struct TextureDetailCache
{
    std::mutex mutex;
    std::unordered_map<const void *, std::pair<std::weak_ptr<const std::vector<unsigned char>>, TextureDetail>> entries;
};
TextureDetailCache g_texture_detail_cache;
} // namespace

float adjustment_blur_radius(float blur, int width, int height)
{
    if (blur <= 0.f || width <= 0 || height <= 0)
        return 0.f;
    const float span = SOURCE_BLUR_SPAN * float(std::min(width, height));
    return std::clamp(blur, 0.f, 1.f) * std::min(span, SOURCE_BLUR_MAX_PX);
}

DecodedHeightTexture downscale_height_texture(const DecodedHeightTexture &src, int max_px)
{
    if (src.empty() || max_px <= 0 || (src.width <= max_px && src.height <= max_px))
        return src;

    const int  scale = std::max(1, (std::max(src.width, src.height) + max_px - 1) / max_px);
    const int  w     = std::max(1, src.width / scale);
    const int  h     = std::max(1, src.height / scale);
    const bool color = src.has_color();

    DecodedHeightTexture out;
    out.width  = w;
    out.height = h;
    out.pixels.resize(size_t(w) * size_t(h));
    if (color)
        out.rgb.resize(size_t(w) * size_t(h) * 3);

    tbb::parallel_for(tbb::blocked_range<int>(0, h), [&](const tbb::blocked_range<int> &r) {
        for (int y = r.begin(); y < r.end(); ++y)
            for (int x = 0; x < w; ++x) {
                // The source block this destination texel covers. The max() keeps the block non-empty
                // when rounding would otherwise collapse it.
                const int x0 = x * src.width / w, x1 = std::max(x0 + 1, (x + 1) * src.width / w);
                const int y0 = y * src.height / h, y1 = std::max(y0 + 1, (y + 1) * src.height / h);
                uint32_t  sum_h = 0, sum_c[3] = { 0, 0, 0 }, n = 0;
                for (int sy = y0; sy < y1 && sy < src.height; ++sy)
                    for (int sx = x0; sx < x1 && sx < src.width; ++sx, ++n) {
                        const size_t si = size_t(sy) * size_t(src.width) + size_t(sx);
                        sum_h += src.pixels[si];
                        if (color)
                            for (int c = 0; c < 3; ++c)
                                sum_c[c] += src.rgb[si * 3 + size_t(c)];
                    }
                const size_t di = size_t(y) * size_t(w) + size_t(x);
                out.pixels[di]  = n > 0 ? uint8_t(sum_h / n) : 0;
                if (color)
                    for (int c = 0; c < 3; ++c)
                        out.rgb[di * 3 + size_t(c)] = n > 0 ? uint8_t(sum_c[c] / n) : 0;
            }
    });
    return out;
}

DecodedHeightTexture apply_texture_adjustments(const DecodedHeightTexture &src, const TextureAdjustments &adj)
{
    DecodedHeightTexture out = src;
    if (src.empty() || adj.identity())
        return out;

    const int    w = out.width;
    const int    h = out.height;
    const size_t n = size_t(w) * size_t(h);

    const float brightness = std::clamp(adj.brightness, -1.f, 1.f);
    // Short of 1, so apply_contrast()'s gain stays finite; at this value it is already a 1000x slope,
    // i.e. a threshold in all but name.
    const float contrast   = std::clamp(adj.contrast, -1.f, 0.999f);
    const float blur       = std::clamp(adj.blur, 0.f, 1.f);
    const float sharpness  = std::clamp(adj.sharpness, 0.f, 1.f);

    // The tonal pass: a 256-entry lookup table, because brightness and contrast are the same scalar
    // curve for every texel and every channel. Building it once beats evaluating two curves a few
    // million times, and it is what keeps this pass off the panel's critical path.
    std::array<uint8_t, 256> tone{};
    for (int i = 0; i < 256; ++i) {
        float v = float(i) / 255.f;
        v       = apply_brightness(v, brightness);
        v       = apply_contrast(v, contrast);
        tone[size_t(i)] = uint8_t(std::lround(std::clamp(v, 0.f, 1.f) * 255.f));
    }

    if (!out.has_color()) {
        // Grayscale: one channel, and hue has nothing to turn.
        tbb::parallel_for(tbb::blocked_range<size_t>(0, n), [&](const tbb::blocked_range<size_t> &r) {
            for (size_t i = r.begin(); i < r.end(); ++i)
                out.pixels[i] = tone[out.pixels[i]];
        });
        adjust_channel_spatial(out.pixels, w, h, blur, sharpness);
        return out;
    }

    // Colour: tone each channel through the same table, then rotate the hue about the luminance axis.
    //
    // The rotation is feColorMatrix's hueRotate matrix (SVG filters), which holds Rec.709 luma fixed.
    // The height below is taken with decode_height_texture()'s Rec.601 coefficients instead, so a hue
    // turn is not perfectly height-neutral - a few levels at full saturation. Reconciling the two would
    // mean a different rotation than every other tool's, which is the worse trade: the user is watching
    // the colour, and the height follows the colour by construction either way.
    const float  theta = adj.hue_deg * float(M_PI) / 180.f;
    const float  c     = std::cos(theta);
    const float  s     = std::sin(theta);
    const float  m[9]  = {
        0.213f + c * 0.787f - s * 0.213f, 0.715f - c * 0.715f - s * 0.715f, 0.072f - c * 0.072f + s * 0.928f,
        0.213f - c * 0.213f + s * 0.143f, 0.715f + c * 0.285f + s * 0.140f, 0.072f - c * 0.072f - s * 0.283f,
        0.213f - c * 0.213f - s * 0.787f, 0.715f - c * 0.715f + s * 0.715f, 0.072f + c * 0.928f + s * 0.072f,
    };
    const bool turn_hue = adj.hue_deg != 0.f;

    tbb::parallel_for(tbb::blocked_range<size_t>(0, n), [&](const tbb::blocked_range<size_t> &r) {
        for (size_t i = r.begin(); i < r.end(); ++i) {
            const float rr = float(tone[out.rgb[i * 3]]);
            const float gg = float(tone[out.rgb[i * 3 + 1]]);
            const float bb = float(tone[out.rgb[i * 3 + 2]]);
            const float nr = turn_hue ? m[0] * rr + m[1] * gg + m[2] * bb : rr;
            const float ng = turn_hue ? m[3] * rr + m[4] * gg + m[5] * bb : gg;
            const float nb = turn_hue ? m[6] * rr + m[7] * gg + m[8] * bb : bb;
            out.rgb[i * 3]     = uint8_t(std::lround(std::clamp(nr, 0.f, 255.f)));
            out.rgb[i * 3 + 1] = uint8_t(std::lround(std::clamp(ng, 0.f, 255.f)));
            out.rgb[i * 3 + 2] = uint8_t(std::lround(std::clamp(nb, 0.f, 255.f)));
        }
    });

    // The spatial pass wants one channel at a time (smooth_height_pixels() is a single-channel blur, and
    // reusing it is what keeps this consistent with Smoothing), so de-interleave, filter, re-interleave.
    if (blur > 0.f || sharpness > 0.f) {
        std::vector<uint8_t> channel(n);
        for (int ch = 0; ch < 3; ++ch) {
            for (size_t i = 0; i < n; ++i)
                channel[i] = out.rgb[i * 3 + size_t(ch)];
            adjust_channel_spatial(channel, w, h, blur, sharpness);
            for (size_t i = 0; i < n; ++i)
                out.rgb[i * 3 + size_t(ch)] = channel[i];
        }
    }

    // Height is the luminance of the colour that came out, not the toned luminance of the colour that
    // went in: the two differ once hue rotation or a per-channel clamp has moved the channels around,
    // and a height that disagrees with the colour it is stored next to is the bug this avoids.
    tbb::parallel_for(tbb::blocked_range<size_t>(0, n), [&](const tbb::blocked_range<size_t> &r) {
        for (size_t i = r.begin(); i < r.end(); ++i)
            out.pixels[i] = uint8_t(std::lround(0.299 * out.rgb[i * 3] + 0.587 * out.rgb[i * 3 + 1] +
                                                0.114 * out.rgb[i * 3 + 2]));
    });
    return out;
}
// TRIM: the bake/meshing pipeline (analyze_texture_detail, HeightFieldSampler composition,
// build_texture_displacement and helpers, ~5100 lines incl. the TextureBake includes) excised
// for the plugin-side-only absorption; nothing in the ResourceTexture capability, TextureLibrary
// catalog or the JSON persistence calls it. Restore from upstream 86ab598899 with the gizmo family.

// Project persistence. See the declarations in TextureDisplacement.hpp for why this is JSON rather
// than the cereal stream next to them.
// ---------------------------------------------------------------------------------------------
namespace {

nlohmann::json vec2_to_json(const Vec2f &v) { return nlohmann::json::array({ v.x(), v.y() }); }
nlohmann::json vec3_to_json(const Vec3f &v) { return nlohmann::json::array({ v.x(), v.y(), v.z() }); }

Vec2f vec2_from_json(const nlohmann::json &j, const Vec2f &fallback)
{
    if (!j.is_array() || j.size() != 2)
        return fallback;
    return Vec2f(j[0].get<float>(), j[1].get<float>());
}
Vec3f vec3_from_json(const nlohmann::json &j, const Vec3f &fallback)
{
    if (!j.is_array() || j.size() != 3)
        return fallback;
    return Vec3f(j[0].get<float>(), j[1].get<float>(), j[2].get<float>());
}

// Reads key `k` into `out` when it is present and of the expected type, leaving `out` alone otherwise.
// That "leave it alone" is the whole point: every member starts at its struct default, so a project
// written by an older build simply keeps the defaults for whatever it did not know about.
template<class T> void read(const nlohmann::json &j, const char *k, T &out)
{
    const auto it = j.find(k);
    if (it == j.end())
        return;
    try {
        out = it->get<T>();
    } catch (...) {
    }
}
void read_enum(const nlohmann::json &j, const char *k, int &out)
{
    const auto it = j.find(k);
    if (it != j.end() && it->is_number_integer())
        out = it->get<int>();
}

} // namespace

std::string texture_displacement_layers_to_json(const std::vector<TextureDisplacementLayer> &layers,
                                                const TextureDisplacementOptions            &options)
{
    nlohmann::json root;
    root["version"] = 1;

    nlohmann::json &opt = root["options"];
    opt["displace_border"]    = options.displace_border;
    opt["smooth_enabled"]     = options.smooth_enabled;
    opt["smooth_strength"]    = options.smooth_strength;
    opt["smooth_iterations"]  = options.smooth_iterations;
    opt["smooth_skip_border"] = options.smooth_skip_border;
    opt["pipeline_v2"]        = options.pipeline_v2;
    opt["v2_refine_mm"]       = options.v2_refine_mm;
    opt["v2_regularize"]      = options.v2_regularize;
    opt["v2_max_triangles_k"] = options.v2_max_triangles_k;
    opt["v2_relocate"]        = options.v2_relocate;
    opt["v2_flip_edges"]      = options.v2_flip_edges;
    opt["color_mix_enabled"]  = options.color_mix_enabled;
    opt["color_despeckle"]    = options.color_despeckle;
    opt["color_mix_count"]    = options.color_mix_count;
    opt["active_slot"]        = options.active_slot;
    opt["panel_mode"]         = options.panel_mode;

    nlohmann::json &arr = root["layers"];
    arr                 = nlohmann::json::array();
    for (const TextureDisplacementLayer &l : layers) {
        nlohmann::json j;
        j["slot"]        = l.slot;
        j["name"]        = l.name;
        j["path"]        = l.path;
        j["path_in_3mf"] = l.path_in_3mf;

        j["depth_mm"]     = l.depth_mm;
        j["tiling_scale"] = l.tiling_scale;
        j["rotation_deg"] = l.rotation_deg;
        j["offset"]       = vec2_to_json(l.offset);
        j["invert"]       = l.invert;
        j["midlevel"]     = l.midlevel;
        j["smoothing"]    = l.smoothing;

        j["edge_smoothing"]        = l.edge_smoothing;
        j["edge_smoothing_amount"] = l.edge_smoothing_amount;
        j["auto_connect_islands"]  = l.auto_connect_islands;

        j["tile_enabled"]      = l.tile_enabled;
        j["tile_method"]       = int(l.tile_method);
        j["projection_method"] = int(l.projection_method);
        j["blend_mode"]        = int(l.blend_mode);
        j["color_enabled"]     = l.color_enabled;

        j["lscm_seam_angle_deg"] = l.lscm_seam_angle_deg;
        j["island_padding_mm"]   = l.island_padding_mm;

        j["view_project_right"]      = vec3_to_json(l.view_project_right);
        j["view_project_up"]         = vec3_to_json(l.view_project_up);
        j["view_project_projective"] = l.view_project_projective;
        j["view_project_matrix"]     = l.view_project_matrix;

        // Flat pairs rather than nested arrays: shorter, and the reader can simply ignore a trailing
        // odd element instead of having to validate every sub-array.
        nlohmann::json &seams = j["lscm_seam_edges"];
        seams                 = nlohmann::json::array();
        for (const auto &[a, b] : l.lscm_seam_edges) {
            seams.push_back(a);
            seams.push_back(b);
        }

        nlohmann::json &islands = j["islands"];
        islands                 = nlohmann::json::array();
        for (const TextureIsland &island : l.islands)
            islands.push_back(nlohmann::json::array(
                { island.offset.x(), island.offset.y(), island.rotation_deg, island.scale }));

        j["island_groups"] = l.island_groups;

        nlohmann::json &overrides = j["lscm_uv_overrides"];
        overrides                 = nlohmann::json::array();
        for (const auto &[key, uv] : l.lscm_uv_overrides)
            overrides.push_back(nlohmann::json::array({ key, uv.x(), uv.y() }));

        arr.push_back(std::move(j));
    }
    return root.dump();
}

bool texture_displacement_layers_from_json(const std::string                     &text,
                                           std::vector<TextureDisplacementLayer> &layers,
                                           TextureDisplacementOptions            &options)
{
    nlohmann::json root;
    try {
        root = nlohmann::json::parse(text);
    } catch (...) {
        return false;
    }
    if (!root.is_object())
        return false;

    TextureDisplacementOptions out_options;
    if (const auto it = root.find("options"); it != root.end() && it->is_object()) {
        const nlohmann::json &opt = *it;
        read(opt, "displace_border", out_options.displace_border);
        read(opt, "smooth_enabled", out_options.smooth_enabled);
        read(opt, "smooth_strength", out_options.smooth_strength);
        read(opt, "smooth_iterations", out_options.smooth_iterations);
        read(opt, "smooth_skip_border", out_options.smooth_skip_border);
        read(opt, "pipeline_v2", out_options.pipeline_v2);
        read(opt, "v2_refine_mm", out_options.v2_refine_mm);
        read(opt, "v2_regularize", out_options.v2_regularize);
        read(opt, "v2_max_triangles_k", out_options.v2_max_triangles_k);
        read(opt, "v2_relocate", out_options.v2_relocate);
        read(opt, "v2_flip_edges", out_options.v2_flip_edges);
        read(opt, "color_mix_enabled", out_options.color_mix_enabled);
        read(opt, "color_despeckle", out_options.color_despeckle);
        read(opt, "color_mix_count", out_options.color_mix_count);
        read(opt, "active_slot", out_options.active_slot);
        read(opt, "panel_mode", out_options.panel_mode);
        out_options.active_slot = std::clamp(out_options.active_slot, 0, int(TEXTURE_DISPLACEMENT_MAX_LAYERS) - 1);
        out_options.panel_mode  = std::clamp(out_options.panel_mode, 0, 1);
    }

    std::vector<TextureDisplacementLayer> out_layers;
    // read() skips a value of the wrong type, but the vector, matrix, seam, island and UV-override arrays
    // below read their numbers with get<>(), which throws on one; that rejects the document, like text that
    // does not parse.
    try {
        if (const auto it = root.find("layers"); it != root.end() && it->is_array()) {
            for (const nlohmann::json &j : *it) {
                if (!j.is_object())
                    continue;
                TextureDisplacementLayer l;
                read(j, "slot", l.slot);
                // The panel and the paint masks are indexed by slot, so a layer without a valid one rejects the
                // document rather than reaching them.
                if (l.slot < 0 || l.slot >= int(TEXTURE_DISPLACEMENT_MAX_LAYERS))
                    return false;
                read(j, "name", l.name);
                read(j, "path", l.path);
                read(j, "path_in_3mf", l.path_in_3mf);

                read(j, "depth_mm", l.depth_mm);
                read(j, "tiling_scale", l.tiling_scale);
                read(j, "rotation_deg", l.rotation_deg);
                if (const auto o = j.find("offset"); o != j.end())
                    l.offset = vec2_from_json(*o, l.offset);
                read(j, "invert", l.invert);
                read(j, "midlevel", l.midlevel);
                read(j, "smoothing", l.smoothing);

                read(j, "edge_smoothing", l.edge_smoothing);
                read(j, "edge_smoothing_amount", l.edge_smoothing_amount);
                read(j, "auto_connect_islands", l.auto_connect_islands);

                read(j, "tile_enabled", l.tile_enabled);
                read(j, "color_enabled", l.color_enabled);
                int tile_method = int(l.tile_method), projection = int(l.projection_method), blend = int(l.blend_mode);
                read_enum(j, "tile_method", tile_method);
                read_enum(j, "projection_method", projection);
                read_enum(j, "blend_mode", blend);
                l.tile_method       = TextureTileMethod(tile_method);
                l.projection_method = TextureProjectionMethod(std::clamp(projection, 0, 4));
                l.blend_mode        = TextureBlendMode(blend);

                read(j, "lscm_seam_angle_deg", l.lscm_seam_angle_deg);
                read(j, "island_padding_mm", l.island_padding_mm);

                if (const auto v = j.find("view_project_right"); v != j.end())
                    l.view_project_right = vec3_from_json(*v, l.view_project_right);
                if (const auto v = j.find("view_project_up"); v != j.end())
                    l.view_project_up = vec3_from_json(*v, l.view_project_up);
                read(j, "view_project_projective", l.view_project_projective);
                if (const auto v = j.find("view_project_matrix"); v != j.end() && v->is_array() && v->size() == 12)
                    for (size_t i = 0; i < 12; ++i)
                        l.view_project_matrix[i] = (*v)[i].get<float>();

                if (const auto v = j.find("lscm_seam_edges"); v != j.end() && v->is_array())
                    for (size_t i = 0; i + 1 < v->size(); i += 2)
                        l.lscm_seam_edges.emplace_back((*v)[i].get<int>(), (*v)[i + 1].get<int>());

                if (const auto v = j.find("islands"); v != j.end() && v->is_array())
                    for (const nlohmann::json &e : *v) {
                        if (!e.is_array() || e.size() != 4)
                            continue;
                        TextureIsland island;
                        island.offset       = Vec2f(e[0].get<float>(), e[1].get<float>());
                        island.rotation_deg = e[2].get<float>();
                        island.scale        = e[3].get<float>();
                        l.islands.push_back(island);
                    }

                read(j, "island_groups", l.island_groups);

                if (const auto v = j.find("lscm_uv_overrides"); v != j.end() && v->is_array())
                    for (const nlohmann::json &e : *v) {
                        if (!e.is_array() || e.size() != 3)
                            continue;
                        l.lscm_uv_overrides.emplace_back(e[0].get<int>(), Vec2f(e[1].get<float>(), e[2].get<float>()));
                    }

                out_layers.push_back(std::move(l));
            }
        }
    } catch (const nlohmann::json::exception &) {
        return false;
    }

    layers  = std::move(out_layers);
    options = out_options;
    return true;
}

} // namespace Slic3r
