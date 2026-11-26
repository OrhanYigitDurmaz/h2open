// Tests for the windows, run without a display (QT_QPA_PLATFORM=offscreen).
#include "api.h"
#include "appearance.h"
#include "loginwindow.h"
#include "mainwindow.h"

#include <QApplication>
#include <QLabel>
#include <QLineEdit>
#include <QMenu>
#include <QPushButton>
#include <QSettings>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QStyle>
#include <QTest>
#include <QToolButton>

#include <memory>

using namespace Qt::StringLiterals;

namespace {

/// A part of the login window, found by its object name.
template <typename T> T *part(const h2open::LoginWindow &window, const QString &name)
{
    auto *found = window.findChild<T *>(name);
    if (found == nullptr) {
        qFatal().noquote() << u"the login window has no"_s << name;
    }
    return found;
}

class TestWindows : public QObject {
    Q_OBJECT

public:
    explicit TestWindows(QObject *parent = nullptr) : QObject(parent) {}

private slots:
    static void initTestCase()
    {
        // Settings go to a scratch place, not the user's own, and in the INI
        // format the app uses (main.cpp).
        QStandardPaths::setTestModeEnabled(true);
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings().clear();
    }

    static void theLoginWindowIsFixedAt800By600()
    {
        const h2open::LoginWindow window;
        QCOMPARE(window.minimumSize(), QSize(800, 600));
        QCOMPARE(window.maximumSize(), QSize(800, 600));
    }

    static void enterMovesOnThenLogsIn()
    {
        h2open::LoginWindow window;
        window.show();
        QVERIFY(QTest::qWaitForWindowActive(&window));
        QSignalSpy submitted(&window, &h2open::LoginWindow::submitted);
        auto *username = part<QLineEdit>(window, u"username"_s);
        auto *password = part<QLineEdit>(window, u"password"_s);

        QTest::keyClicks(username, u"  ayse "_s);
        QTest::keyClick(username, Qt::Key_Return);
        QVERIFY(password->hasFocus());
        QTest::keyClicks(password, u"secret"_s);
        QTest::keyClick(password, Qt::Key_Return);

        QCOMPARE(submitted.count(), 1);
        QCOMPARE(submitted.first(), (QVariantList{u"ayse"_s, u"secret"_s}));
        // Busy until the server answers.
        QVERIFY(!username->isEnabled());
        QVERIFY(!part<QPushButton>(window, u"submit"_s)->isEnabled());
    }

    static void emptyFieldsAreNotSent()
    {
        h2open::LoginWindow window;
        window.show();
        const QSignalSpy submitted(&window, &h2open::LoginWindow::submitted);
        QTest::mouseClick(part<QPushButton>(window, u"submit"_s), Qt::LeftButton);
        QCOMPARE(submitted.count(), 0);
        QVERIFY(part<QLabel>(window, u"error"_s)->isVisible());
    }

    static void aFailedLoginCanBeRetried()
    {
        h2open::LoginWindow window;
        window.show();
        auto *password = part<QLineEdit>(window, u"password"_s);
        QTest::keyClicks(part<QLineEdit>(window, u"username"_s), u"ayse"_s);
        QTest::keyClicks(password, u"wrong"_s);
        QTest::mouseClick(part<QPushButton>(window, u"submit"_s), Qt::LeftButton);

        window.showError(h2open::message({.reason = h2open::LoginFailure::Reason::Refused}));
        QVERIFY(password->text().isEmpty());
        QVERIFY(password->isEnabled());
        QVERIFY(part<QLabel>(window, u"error"_s)->text().startsWith(u"Wrong username"));
    }

    static void theDarkPaletteHasTheDesignedColours()
    {
        const QPalette palette = h2open::darkPalette();
        QCOMPARE(palette.color(QPalette::Active, QPalette::Window), QColor(25, 25, 25));
        QCOMPARE(palette.color(QPalette::Active, QPalette::ButtonText), QColor(u"#8ab4f7"_s));
        QCOMPARE(palette.color(QPalette::Active, QPalette::Highlight), QColor(u"#8ab4f7"_s));
        // Colours set without a group apply to every group...
        QCOMPARE(palette.color(QPalette::Disabled, QPalette::Window), QColor(25, 25, 25));
        // ...unless a group sets its own.
        QCOMPARE(palette.color(QPalette::Disabled, QPalette::Text), QColor(u"#697177"_s));
        QCOMPARE(palette.color(QPalette::Inactive, QPalette::Highlight), QColor(u"#393d41"_s));
    }

    static void schemesAreSavedByName()
    {
        for (const auto scheme :
             {Qt::ColorScheme::Dark, Qt::ColorScheme::Light, Qt::ColorScheme::Unknown}) {
            QCOMPARE(h2open::schemeFromName(h2open::schemeName(scheme)), scheme);
        }
        QCOMPARE(h2open::schemeName(Qt::ColorScheme::Unknown), u"system"_s);
        QCOMPARE(h2open::schemeFromName(u"purple"), std::nullopt);
    }

    static void theSavedSchemeIsUsedAtStart()
    {
        QSettings().setValue(u"appearance/colorScheme"_s, u"light"_s);
        h2open::Appearance::setUp();
        QCOMPARE(QApplication::style()->name().toLower(), u"fusion"_s);
        QCOMPARE(h2open::Appearance::instance().colorScheme(), Qt::ColorScheme::Light);
        QCOMPARE(QApplication::palette(), QApplication::style()->standardPalette());
    }

    static void aBrokenSettingFallsBackToDark()
    {
        QSettings().setValue(u"appearance/colorScheme"_s, u"purple"_s);
        h2open::Appearance::setUp();
        QCOMPARE(h2open::Appearance::instance().colorScheme(), Qt::ColorScheme::Dark);
        QCOMPARE(QApplication::palette().color(QPalette::Window), QColor(25, 25, 25));
    }

    static void theThemeMenuChangesAndFollowsTheScheme()
    {
        h2open::Appearance &appearance = h2open::Appearance::instance();
        appearance.setColorScheme(Qt::ColorScheme::Dark);
        const std::unique_ptr<QMenu> menu{h2open::createThemeMenu(nullptr)};
        const QList<QAction *> actions = menu->actions();
        QCOMPARE(actions.size(), 3);
        QVERIFY(actions.at(0)->isChecked());

        // Picking "Light" in the menu switches, and is saved.
        actions.at(1)->trigger();
        QCOMPARE(appearance.colorScheme(), Qt::ColorScheme::Light);
        const QSettings settings;
        QCOMPARE(settings.value(u"appearance/colorScheme"_s).toString(), u"light"_s);
        QCOMPARE(settings.format(), QSettings::IniFormat);
        QVERIFY(settings.fileName().endsWith(u".ini"));

        // A change made elsewhere (another window's menu) shows here too.
        appearance.setColorScheme(Qt::ColorScheme::Unknown);
        QVERIFY(actions.at(2)->isChecked());
        QVERIFY(!actions.at(1)->isChecked());
        appearance.setColorScheme(Qt::ColorScheme::Dark);
    }

    static void theLoginWindowHasAThemeMenu()
    {
        const h2open::LoginWindow window;
        const auto *button = window.findChild<QToolButton *>(u"theme"_s);
        QVERIFY(button != nullptr && button->menu() != nullptr);
    }

    static void theMainWindowOpensWithTheGallery()
    {
        // Builds every widget in the gallery, under the sanitizers.
        h2open::MainWindow window({.username = u"ayse"_s, .name = u"Ayşe Yılmaz"_s});
        window.show();
        QVERIFY(QTest::qWaitForWindowExposed(&window));
        const QSignalSpy logout(&window, &h2open::MainWindow::logoutRequested);
        const auto actions = window.findChildren<QAction *>();
        const auto found = std::ranges::find(actions, u"Log out"_s, &QAction::text);
        QVERIFY(found != actions.end());
        (*found)->trigger();
        QCOMPARE(logout.count(), 1);
    }
};

} // namespace

QTEST_MAIN(TestWindows)
// Generated by moc: not ours, and it indexes raw pointer arrays by design.
#ifdef __clang__
#pragma clang unsafe_buffer_usage begin
#endif
#include "test_windows.moc"
#ifdef __clang__
#pragma clang unsafe_buffer_usage end
#endif
