// Calls to the h2open server.
#pragma once

#include <QByteArray>
#include <QNetworkAccessManager>
#include <QObject>
#include <QString>
#include <QUrl>

#include <cstdint>
#include <optional>

class QNetworkReply;

namespace h2open {

/// The user account behind a login.
struct User {
    QString username;
    QString name;
};

/// A logged-in user and the token for their requests.
struct Session {
    /// Sent as `Authorization: Bearer <token>`. Kept in memory only.
    QString token;
    User user;
};

/// Why logging in did not work.
struct LoginFailure {
    enum class Reason : std::uint8_t {
        /// The server refused the username or password (it never says which).
        Refused,
        /// The server could not be reached.
        Unreachable,
        /// The server answered something unexpected.
        Server,
    };
    Reason reason = Reason::Server;
    /// The HTTP status, for `Server`.
    int status = 0;
};

/// What to tell the user about a failed login.
[[nodiscard]] QString message(const LoginFailure &failure);

/// What a login answer's status means: nothing for success, else the failure.
///
/// 401 is a wrong username or password, or a locked account; 422 is a
/// password longer than any valid one, so it is the same to the user.
[[nodiscard]] std::optional<LoginFailure> checkLoginStatus(int status);

/// Read the server's login result; nothing if it is not one.
[[nodiscard]] std::optional<Session> parseSession(const QByteArray &body);

/// The login request body, as the desktop app.
[[nodiscard]] QByteArray loginBody(const QString &username, const QString &password,
                                   const QString &clientName);

/// This computer's name, shown in the user's list of logins.
[[nodiscard]] QString clientName();

/// `base` without trailing slashes, e.g. `http://10.0.0.2:8000`.
[[nodiscard]] QString normalizeBaseUrl(const QString &base);

/// A connection to the h2open server. Calls are asynchronous: results come
/// back as signals on the UI thread.
class ApiClient : public QObject {
    Q_OBJECT

public:
    /// A client for `baseUrl`, e.g. `https://pos.example:8000` or
    /// `http://10.0.0.2:8000`.
    explicit ApiClient(const QString &baseUrl, QObject *parent = nullptr);

    /// The server at `H2OPEN_SERVER_URL`, or this computer.
    [[nodiscard]] static QString serverUrlFromEnvironment();

    [[nodiscard]] const QString &baseUrl() const { return m_baseUrl; }

    /// Log in; answers with `loggedIn` or `loginFailed`.
    void login(const QString &username, const QString &password);

    /// End a login on the server. Failures are ignored: the token is
    /// forgotten either way, and the server expires it in time. The reply
    /// deletes itself when it finishes.
    QNetworkReply *logout(const QString &token);

signals:
    void loggedIn(const h2open::Session &session);
    void loginFailed(const h2open::LoginFailure &failure);

private:
    [[nodiscard]] QUrl endpoint(const QString &path) const;

    QString m_baseUrl;
    QNetworkAccessManager m_network;
};

} // namespace h2open
