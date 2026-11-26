#include "desktopapp.h"

#include <QApplication>
#include <QNetworkReply>
#include <QTimer>

#include <chrono>

namespace h2open {

namespace {

/// How long quitting waits for the server to end the login.
constexpr std::chrono::seconds logoutGrace{3};

} // namespace

DesktopApp::DesktopApp(QObject *parent)
    : QObject(parent), m_client(ApiClient::serverUrlFromEnvironment(), this),
      m_login(new LoginWindow)
{
    // Quitting is decided here: closing the main window logs out first.
    QApplication::setQuitOnLastWindowClosed(false);

    connect(m_login.get(), &LoginWindow::submitted, &m_client, &ApiClient::login);
    connect(m_login.get(), &LoginWindow::closed, qApp, &QCoreApplication::quit);
    connect(&m_client, &ApiClient::loggedIn, this, &DesktopApp::openApp);
    connect(&m_client, &ApiClient::loginFailed, m_login.get(),
            [this](LoginFailure failure) { m_login->showError(message(failure)); });
}

void DesktopApp::start()
{
    m_login->show();
}

void DesktopApp::openApp(const Session &session)
{
    m_session = session;
    m_main = QObjectPtr<MainWindow>(new MainWindow(session.user));
    connect(m_main.get(), &MainWindow::logoutRequested, this, &DesktopApp::logout);
    connect(m_main.get(), &MainWindow::closed, this, &DesktopApp::quitLoggedIn);
    m_main->showMaximized();
    m_login->hide();
    m_login->clearForm();
}

void DesktopApp::logout()
{
    m_login->show();
    if (m_main) {
        // Called from the main window's own signal, so it is deleted later.
        m_main->disconnect(this);
        m_main.reset();
    }
    if (m_session) {
        m_client.logout(m_session->token);
        m_session.reset();
    }
}

void DesktopApp::quitLoggedIn()
{
    if (!m_session) {
        QCoreApplication::quit();
        return;
    }
    const QNetworkReply *reply = m_client.logout(m_session->token);
    m_session.reset();
    connect(reply, &QNetworkReply::finished, qApp, &QCoreApplication::quit);
    // Do not hang on a server that does not answer.
    QTimer::singleShot(logoutGrace, qApp, &QCoreApplication::quit);
}

} // namespace h2open
