#ifndef slic3r_App_AccountViewModel_hpp_
#define slic3r_App_AccountViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>

namespace Slic3r {

/// Login/account state.
enum class LoginState {
    LoggedOut,
    LoggingIn,
    LoggedIn,
    Error,
};

/// MVVP ViewModel for user account/authentication (extracted from GUI_App).
class AccountViewModel {
public:
    // ?? Observable State ??
    MVVP::Property<LoginState>  loginState{LoginState::LoggedOut};
    MVVP::Property<std::string> userName{""};
    MVVP::Property<std::string> userAvatar{""};
    MVVP::Property<bool>        isVip{false};

    // ?? Commands ??
    MVVP::Command login{
        [this] { loginState.set(LoginState::LoggingIn); },
        [this] { return loginState.get() == LoginState::LoggedOut; }
    };
    MVVP::Command logout{
        [this] { loginState.set(LoginState::LoggedOut); userName.set(""); },
        [this] { return loginState.get() == LoginState::LoggedIn; }
    };

    // ?? Interface ??
    void onLoginSuccess(const std::string& name, const std::string& avatar);
    void onLoginError(const std::string& error);
};

} // namespace Slic3r

#endif /* slic3r_App_AccountViewModel_hpp_ */
