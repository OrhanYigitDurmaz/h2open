// Both windows: the login window and, after a login, the main window.
// Only one is open at a time.
#pragma once

#include "api.h"

#include <QObject>
#include <QPointer>

#include <optional>

namespace h2open {

class LoginWindow;
class MainWindow;

class DesktopApp : public QObject {
    Q_OBJECT

public:
    explicit DesktopApp(QObject *parent = nullptr);
    ~DesktopApp() override;

    DesktopApp(const DesktopApp &) = delete;
    DesktopApp &operator=(const DesktopApp &) = delete;
    DesktopApp(DesktopApp &&) = delete;
    DesktopApp &operator=(DesktopApp &&) = delete;

    /// Show the login window.
    void start();

private:
    void openApp(const Session &session);
    void logout();
    /// The main window was closed: end the login, then quit.
    void quitLoggedIn();

    ApiClient m_client;
    LoginWindow *m_login;
    QPointer<MainWindow> m_main;
    /// The login in use. The token is kept in memory only.
    std::optional<Session> m_session;
};

} // namespace h2open
