// Tests for the server calls in src/api.cpp.
#include "api.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTest>

using namespace Qt::StringLiterals;
using h2open::LoginFailure;

class TestApi : public QObject {
    Q_OBJECT

private slots:
    static void statusesMapToWhatTheUserIsTold()
    {
        QVERIFY(!h2open::checkLoginStatus(200).has_value());
        QCOMPARE(h2open::checkLoginStatus(401)->reason, LoginFailure::Reason::Refused);
        QCOMPARE(h2open::checkLoginStatus(422)->reason, LoginFailure::Reason::Refused);
        const auto server = h2open::checkLoginStatus(500);
        QCOMPARE(server->reason, LoginFailure::Reason::Server);
        QCOMPARE(server->status, 500);
    }

    static void readsTheServersLoginResult()
    {
        const QByteArray body = R"({
            "token": "abc",
            "expires_at": "2026-12-26T17:00:00Z",
            "user": {
                "id": "0193b2c0-0000-7000-8000-000000000000",
                "username": "ayse",
                "name": "Ayşe Yılmaz",
                "roles": ["staff"],
                "active": true,
                "on_shift": false
            }
        })";
        const auto session = h2open::parseSession(body);
        QVERIFY(session.has_value());
        QCOMPARE(session->token, u"abc"_s);
        QCOMPARE(session->user.username, u"ayse"_s);
        QCOMPARE(session->user.name, u"Ayşe Yılmaz"_s);
    }

    static void anythingElseIsNotALoginResult()
    {
        QVERIFY(!h2open::parseSession("not json").has_value());
        QVERIFY(!h2open::parseSession(R"({"token": "abc"})").has_value());
        QVERIFY(!h2open::parseSession(R"({"user": {"username": "ayse"}})").has_value());
    }

    static void sendsWhatTheServerExpects()
    {
        const QJsonObject body =
            QJsonDocument::fromJson(h2open::loginBody(u"ayse"_s, u"secret"_s, u"POS 1"_s)).object();
        QCOMPARE(body, (QJsonObject{
                           {u"username"_s, u"ayse"_s},
                           {u"password"_s, u"secret"_s},
                           {u"platform"_s, u"desktop"_s},
                           {u"client_name"_s, u"POS 1"_s},
                       }));
        const QJsonObject unnamed =
            QJsonDocument::fromJson(h2open::loginBody(u"ayse"_s, u"x"_s, QString())).object();
        QVERIFY(unnamed.value(u"client_name").isNull());
    }

    static void trailingSlashesAreDropped()
    {
        QCOMPARE(h2open::normalizeBaseUrl(u"http://pos:8000//"_s), u"http://pos:8000"_s);
        QCOMPARE(h2open::ApiClient(u" http://pos:8000/ "_s).baseUrl(), u"http://pos:8000"_s);
    }

    static void anUnreachableServerIsReported()
    {
        // Port 9 (discard) on this computer: nothing listens, so it is refused.
        h2open::ApiClient client(u"http://127.0.0.1:9"_s);
        QSignalSpy failed(&client, &h2open::ApiClient::loginFailed);
        const QSignalSpy succeeded(&client, &h2open::ApiClient::loggedIn);
        client.login(u"ayse"_s, u"x"_s);
        QVERIFY(failed.wait(5000));
        QCOMPARE(failed.first().first().value<LoginFailure>().reason,
                 LoginFailure::Reason::Unreachable);
        QCOMPARE(succeeded.count(), 0);
    }

    static void everyFailureHasAMessage()
    {
        for (const auto reason : {
                 LoginFailure::Reason::Refused,
                 LoginFailure::Reason::Unreachable,
                 LoginFailure::Reason::Server,
             }) {
            QVERIFY(h2open::message({.reason = reason, .status = 502}).endsWith(u'.'));
        }
        QVERIFY(h2open::message({.reason = LoginFailure::Reason::Server, .status = 502})
                    .contains(u"502"));
    }
};

QTEST_GUILESS_MAIN(TestApi)
#include "test_api.moc"
