// Both windows: the login window and, after a login, the main window.
// Only one is open at a time.
#pragma once

#include "api.h"
#include "loginwindow.h"
#include "mainwindow.h"
#include "qtmemory.h"

#include <QObject>

#include <optional>

namespace h2open {

class DesktopApp : public QObject {
    Q_OBJECT

public:
    explicit DesktopApp(QObject *parent = nullptr);

    /// Show the login window.
    void start();

private:
    void openApp(const Session &session);
    void logout();
    /// The main window was closed: end the login, then quit.
    void quitLoggedIn();

    ApiClient m_client;
    /// Top-level windows have no parent, so they are owned here.
    QObjectPtr<LoginWindow> m_login;
    QObjectPtr<MainWindow> m_main;
    /// The login in use. The token is kept in memory only.
    std::optional<Session> m_session;
};

} // namespace h2open
