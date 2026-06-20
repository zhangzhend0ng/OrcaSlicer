#include "catch2/catch.hpp"
#include "slic3r/App/AppViewModel.hpp"
#include "slic3r/App/PresetViewModel.hpp"
#include "slic3r/App/DeviceViewModel.hpp"
#include "slic3r/App/SettingsViewModel.hpp"
#include "slic3r/App/AccountViewModel.hpp"
#include "slic3r/App/PluginViewModel.hpp"

using namespace Slic3r;

TEST_CASE("AppViewModel default page is Prepare", "[AppViewModel][MVVP]") {
    AppViewModel avm;
    REQUIRE(avm.currentPage.get() == AppPage::Prepare);
    REQUIRE_FALSE(avm.isInitialized.get());
}

TEST_CASE("AppViewModel page navigation", "[AppViewModel][MVVP]") {
    AppViewModel avm;
    avm.showDevice.execute();
    REQUIRE(avm.currentPage.get() == AppPage::Device);
    avm.showPreview.execute();
    REQUIRE(avm.currentPage.get() == AppPage::Preview);
    avm.showPrepare.execute();
    REQUIRE(avm.currentPage.get() == AppPage::Prepare);
}

TEST_CASE("AppViewModel sub-ViewModels exist", "[AppViewModel][MVVP]") {
    AppViewModel avm;
    REQUIRE(avm.platerVM != nullptr);
    REQUIRE(avm.canvasVM != nullptr);
    REQUIRE(avm.presetVM != nullptr);
    REQUIRE(avm.deviceVM != nullptr);
    REQUIRE(avm.settingsVM != nullptr);
    REQUIRE(avm.accountVM != nullptr);
    REQUIRE(avm.pluginVM != nullptr);
}

TEST_CASE("PresetViewModel default state", "[PresetViewModel][MVVP]") {
    PresetViewModel pvm;
    REQUIRE(pvm.printPresets.get().empty());
    REQUIRE_FALSE(pvm.hasUnsavedChanges.get());
    REQUIRE_FALSE(pvm.savePreset.canExecute());
}

TEST_CASE("DeviceViewModel empty device list", "[DeviceViewModel][MVVP]") {
    DeviceViewModel dvm;
    REQUIRE(dvm.devices.get().empty());
    REQUIRE_FALSE(dvm.isScanning.get());
    REQUIRE(dvm.scanNetwork.canExecute());
}

TEST_CASE("SettingsViewModel apply requires dirty", "[SettingsViewModel][MVVP]") {
    SettingsViewModel svm;
    REQUIRE_FALSE(svm.applySettings.canExecute());
    svm.isDirty.set(true);
    REQUIRE(svm.applySettings.canExecute());
}

TEST_CASE("AccountViewModel login flow", "[AccountViewModel][MVVP]") {
    AccountViewModel avm;
    REQUIRE(avm.loginState.get() == LoginState::LoggedOut);
    avm.login.execute();
    REQUIRE(avm.loginState.get() == LoginState::LoggingIn);
    avm.onLoginSuccess("test_user", "");
    REQUIRE(avm.loginState.get() == LoginState::LoggedIn);
    REQUIRE(avm.userName.get() == "test_user");
}

TEST_CASE("PluginViewModel toggle needs selection", "[PluginViewModel][MVVP]") {
    PluginViewModel pvm;
    REQUIRE_FALSE(pvm.toggleSelected.canExecute());
}
