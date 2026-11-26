#include "appearance.h"

#include <QActionGroup>
#include <QApplication>
#include <QColor>
#include <QMenu>
#include <QSettings>
#include <QStyle>
#include <QStyleHints>

#include <array>
#include <utility>

using namespace Qt::StringLiterals;

namespace h2open {

namespace {

/// Where the choice is saved, in QSettings.
constexpr auto settingsKey = u"appearance/colorScheme";

struct SchemeChoice {
    Qt::ColorScheme scheme = Qt::ColorScheme::Dark;
    QStringView name;
    QStringView label;
};

/// The choices, in menu order.
constexpr std::array<SchemeChoice, 3> choices{
    SchemeChoice{.scheme = Qt::ColorScheme::Dark, .name = u"dark", .label = u"&Dark"},
    SchemeChoice{.scheme = Qt::ColorScheme::Light, .name = u"light", .label = u"&Light"},
    SchemeChoice{
        .scheme = Qt::ColorScheme::Unknown,
        .name = u"system",
        .label = u"Follow the &system",
    },
};

/// Dark or light, after resolving "follow the system".
bool wantsDark(Qt::ColorScheme scheme)
{
    if (scheme == Qt::ColorScheme::Unknown) {
        return QGuiApplication::styleHints()->colorScheme() == Qt::ColorScheme::Dark;
    }
    return scheme == Qt::ColorScheme::Dark;
}

} // namespace

QPalette darkPalette()
{
    // Not quite white (#fefefe): the original palette for PyQt6 used it to work
    // around a PyQt bug; kept so both look the same.
    const QColor white(u"#fefefe"_s);
    // A little blue on button text and highlights makes clear what is
    // clickable.
    const QColor subtleBlue(u"#8ab4f7"_s);

    QPalette palette;
    // Every group (active, inactive, disabled), unless set again below.
    palette.setColor(QPalette::Window, QColor(25, 25, 25));
    palette.setColor(QPalette::WindowText, white);
    palette.setColor(QPalette::Base, QColor(5, 5, 5));
    palette.setColor(QPalette::AlternateBase, QColor(10, 10, 10));
    palette.setColor(QPalette::ToolTipBase, QColor(0, 0, 0));
    palette.setColor(QPalette::ToolTipText, white);
    palette.setColor(QPalette::Text, white);
    palette.setColor(QPalette::Button, QColor(20, 20, 20));
    palette.setColor(QPalette::ButtonText, subtleBlue);
    palette.setColor(QPalette::BrightText, white);
    palette.setColor(QPalette::Link, QColor(42, 130, 218));
    palette.setColor(QPalette::Highlight, subtleBlue);
    palette.setColor(QPalette::HighlightedText, white);
    palette.setColor(QPalette::PlaceholderText, QColor(180, 180, 180));

    // The shades Fusion draws bevels, frames and separators with.
    palette.setColor(QPalette::Light, QColor(25, 25, 25));
    palette.setColor(QPalette::Midlight, QColor(30, 30, 30));
    palette.setColor(QPalette::Dark, QColor(228, 228, 228));
    palette.setColor(QPalette::Mid, QColor(63, 63, 63));
    palette.setColor(QPalette::Shadow, QColor(63, 63, 63));

    const QColor disabledText(u"#697177"_s);
    palette.setColor(QPalette::Disabled, QPalette::WindowText, disabledText);
    palette.setColor(QPalette::Disabled, QPalette::Text, disabledText);
    palette.setColor(QPalette::Disabled, QPalette::ButtonText, QColor(u"#3f4042"_s));
    palette.setColor(QPalette::Disabled, QPalette::Highlight, QColor(u"#53575b"_s));
    palette.setColor(QPalette::Disabled, QPalette::HighlightedText, disabledText);
    palette.setColor(QPalette::Disabled, QPalette::Link, disabledText);
    palette.setColor(QPalette::Disabled, QPalette::LinkVisited, disabledText);

    // A dimmer selection in windows that are not focused.
    palette.setColor(QPalette::Inactive, QPalette::Highlight, QColor(u"#393d41"_s));
    return palette;
}

QString schemeName(Qt::ColorScheme scheme)
{
    for (const SchemeChoice &choice : choices) {
        if (choice.scheme == scheme) {
            return choice.name.toString();
        }
    }
    return u"dark"_s;
}

std::optional<Qt::ColorScheme> schemeFromName(QStringView name)
{
    for (const SchemeChoice &choice : choices) {
        if (choice.name == name) {
            return choice.scheme;
        }
    }
    return std::nullopt;
}

Appearance::Appearance(QObject *parent) : QObject(parent)
{
    // When the system switches between light and dark, follow it if asked to.
    connect(QGuiApplication::styleHints(), &QStyleHints::colorSchemeChanged, this, [this] {
        if (m_scheme == Qt::ColorScheme::Unknown) {
            reapply();
        }
    });
}

Appearance &Appearance::instance()
{
    // Owned by the application, so it goes when the application does.
    static auto *const appearance = new Appearance(QCoreApplication::instance());
    return *appearance;
}

void Appearance::setUp()
{
    QApplication::setStyle(u"Fusion"_s);
    const QString saved = QSettings().value(settingsKey).toString();
    instance().setColorScheme(schemeFromName(saved).value_or(Qt::ColorScheme::Dark));
}

void Appearance::setColorScheme(Qt::ColorScheme scheme)
{
    m_scheme = scheme;
    // Title bars and other system-drawn parts; `Unknown` gives it back to the
    // system.
    QGuiApplication::styleHints()->setColorScheme(scheme);
    reapply();
    QSettings().setValue(settingsKey, schemeName(scheme));
    emit colorSchemeChanged(scheme);
}

void Appearance::reapply() const
{
    QApplication::setPalette(wantsDark(m_scheme) ? darkPalette()
                                                 : QApplication::style()->standardPalette());
}

QMenu *createThemeMenu(QWidget *parent)
{
    auto *menu = new QMenu(u"&Theme"_s, parent);
    auto *group = new QActionGroup(menu);
    const Appearance &appearance = Appearance::instance();
    for (const SchemeChoice &choice : choices) {
        QAction *action = menu->addAction(choice.label.toString());
        action->setCheckable(true);
        action->setData(QVariant::fromValue(choice.scheme));
        action->setChecked(choice.scheme == appearance.colorScheme());
        group->addAction(action);
        QObject::connect(action, &QAction::triggered, menu, [scheme = choice.scheme] {
            Appearance::instance().setColorScheme(scheme);
        });
    }
    // Changed from another menu (the login window's, or the main window's).
    QObject::connect(&appearance, &Appearance::colorSchemeChanged, menu,
                     [group](Qt::ColorScheme scheme) {
                         const QList<QAction *> actions = group->actions();
                         for (QAction *action : actions) {
                             action->setChecked(action->data().value<Qt::ColorScheme>() == scheme);
                         }
                     });
    return menu;
}

} // namespace h2open
