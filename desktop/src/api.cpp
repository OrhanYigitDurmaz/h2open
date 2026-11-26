#include "api.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QSysInfo>

#include <chrono>

using namespace Qt::StringLiterals;

namespace h2open {

namespace {

/// Where the server is when `H2OPEN_SERVER_URL` is not set: this computer.
constexpr auto defaultServerUrl = u"http://127.0.0.1:8000";

/// The server's limit on `client_name`.
constexpr qsizetype maxClientName = 100;

constexpr std::chrono::seconds timeout{10};

QNetworkRequest jsonRequest(const QUrl &url)
{
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, u"application/json"_s);
    request.setRawHeader("Accept", "application/json");
    request.setTransferTimeout(timeout);
    return request;
}

} // namespace

QString message(const LoginFailure &failure)
{
    switch (failure.reason) {
    case LoginFailure::Reason::Refused:
        return u"Wrong username or password. After several failed tries the account is "
               "locked for a while."_s;
    case LoginFailure::Reason::Unreachable:
        return u"The h2open server cannot be reached. Check the network and try again."_s;
    case LoginFailure::Reason::Server:
        return u"The h2open server answered %1."_s.arg(failure.status);
    }
    return {};
}

std::optional<LoginFailure> checkLoginStatus(int status)
{
    if (status >= 200 && status < 300) {
        return std::nullopt;
    }
    if (status == 401 || status == 422) {
        return LoginFailure{.reason = LoginFailure::Reason::Refused};
    }
    return LoginFailure{.reason = LoginFailure::Reason::Server, .status = status};
}

std::optional<Session> parseSession(const QByteArray &body)
{
    const QJsonDocument document = QJsonDocument::fromJson(body);
    const QJsonObject root = document.object();
    const QJsonObject user = root.value(u"user").toObject();
    const QString token = root.value(u"token").toString();
    const QString username = user.value(u"username").toString();
    if (token.isEmpty() || username.isEmpty()) {
        return std::nullopt;
    }
    return Session{
        .token = token,
        .user = {.username = username, .name = user.value(u"name").toString()},
    };
}

QByteArray loginBody(const QString &username, const QString &password, const QString &clientName)
{
    QJsonObject body{
        {u"username"_s, username},
        {u"password"_s, password},
        {u"platform"_s, u"desktop"_s},
    };
    body.insert(u"client_name"_s, clientName.isEmpty() ? QJsonValue() : QJsonValue(clientName));
    return QJsonDocument(body).toJson(QJsonDocument::Compact);
}

QString clientName()
{
    return QSysInfo::machineHostName().trimmed().left(maxClientName);
}

QString normalizeBaseUrl(const QString &base)
{
    QString url = base.trimmed();
    while (url.endsWith(u'/')) {
        url.chop(1);
    }
    return url;
}

ApiClient::ApiClient(const QString &baseUrl, QObject *parent)
    : QObject(parent), m_baseUrl(normalizeBaseUrl(baseUrl))
{
}

QString ApiClient::serverUrlFromEnvironment()
{
    const QString url = qEnvironmentVariable("H2OPEN_SERVER_URL");
    return url.isEmpty() ? QString(defaultServerUrl) : url;
}

QUrl ApiClient::endpoint(const QString &path) const
{
    return QUrl(m_baseUrl + path);
}

void ApiClient::login(const QString &username, const QString &password)
{
    QNetworkReply *reply = m_network.post(jsonRequest(endpoint(u"/auth/login"_s)),
                                          loginBody(username, password, clientName()));
    connect(reply, &QNetworkReply::finished, this, [this, reply] {
        reply->deleteLater();
        const QVariant status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute);
        if (!status.isValid()) {
            // No HTTP answer at all: refused, timed out, DNS, TLS...
            emit loginFailed({.reason = LoginFailure::Reason::Unreachable});
            return;
        }
        if (const auto failure = checkLoginStatus(status.toInt())) {
            emit loginFailed(*failure);
            return;
        }
        if (const auto session = parseSession(reply->readAll())) {
            emit loggedIn(*session);
        } else {
            emit loginFailed({.reason = LoginFailure::Reason::Server, .status = status.toInt()});
        }
    });
}

QNetworkReply *ApiClient::logout(const QString &token)
{
    QNetworkRequest request = jsonRequest(endpoint(u"/auth/logout"_s));
    request.setRawHeader("Authorization", "Bearer " + token.toUtf8());
    QNetworkReply *reply = m_network.post(request, QByteArray());
    connect(reply, &QNetworkReply::finished, reply, &QObject::deleteLater);
    return reply;
}

} // namespace h2open
