#include "catch2/catch.hpp"
#include "libslic3r/MVVP.hpp"

using namespace Slic3r::MVVP;

TEST_CASE("Property default construction", "[MVVP]") {
    Property<int> p;
    REQUIRE(p.get() == 0);
}

TEST_CASE("Property initial value", "[MVVP]") {
    Property<int> p(42);
    REQUIRE(p.get() == 42);
}

TEST_CASE("Property set notifies subscribers", "[MVVP]") {
    Property<int> p(10);
    int newVal = 0, oldVal = 0, callCount = 0;

    auto sub = p.subscribe([&](const int& n, const int& o) {
        newVal = n; oldVal = o; callCount++;
    });

    p.set(20);
    REQUIRE(callCount == 1);
    REQUIRE(newVal == 20);
    REQUIRE(oldVal == 10);
}

TEST_CASE("Property multiple subscribers", "[MVVP]") {
    Property<std::string> p("hello");
    int countA = 0, countB = 0;

    auto subA = p.subscribe([&](const auto&, const auto&) { countA++; });
    auto subB = p.subscribe([&](const auto&, const auto&) { countB++; });

    p.set("world");
    REQUIRE(countA == 1);
    REQUIRE(countB == 1);
}

TEST_CASE("Property unsubscribe via Subscription destruction", "[MVVP]") {
    Property<int> p(0);
    int count = 0;

    {
        auto sub = p.subscribe([&](const auto&, const auto&) { count++; });
        p.set(1);
        REQUIRE(count == 1);
    }

    p.set(2);
    REQUIRE(count == 1);
}

TEST_CASE("Property move semantics for Subscription", "[MVVP]") {
    Property<int> p(0);
    int count = 0;

    auto sub1 = p.subscribe([&](const auto&, const auto&) { count++; });
    auto sub2 = std::move(sub1);

    p.set(1);
    REQUIRE(count == 1);
}

TEST_CASE("Property mutate for in-place modification", "[MVVP]") {
    Property<std::vector<int>> p(std::vector<int>{1, 2, 3});

    p.mutate().push_back(4);
    p.notifyMutation();

    REQUIRE(p.get().size() == 4);
    REQUIRE(p.get()[3] == 4);
}

TEST_CASE("Command executes when canExecute returns true", "[MVVP]") {
    bool executed = false;
    Command cmd([&] { executed = true; });

    REQUIRE(cmd.canExecute());
    cmd.execute();
    REQUIRE(executed);
}

TEST_CASE("Command does not execute when canExecute returns false", "[MVVP]") {
    bool executed = false;
    Command cmd(
        [&] { executed = true; },
        [] { return false; }
    );

    REQUIRE_FALSE(cmd.canExecute());
    cmd.execute();
    REQUIRE_FALSE(executed);
}

TEST_CASE("Command canExecute derived from Property", "[MVVP]") {
    Property<int> count(0);
    Command cmd(
        [&count] { count.set(count.get() + 1); },
        [&count] { return count.get() < 3; }
    );

    REQUIRE(cmd.canExecute());
    cmd.execute(); // count=1
    REQUIRE(cmd.canExecute());
    cmd.execute(); // count=2
    REQUIRE(cmd.canExecute());
    cmd.execute(); // count=3
    REQUIRE_FALSE(cmd.canExecute());
    cmd.execute(); // should not execute
    REQUIRE(count.get() == 3);
}
