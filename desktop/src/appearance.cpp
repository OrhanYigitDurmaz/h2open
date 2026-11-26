#include "appearance.h"

#include <QApplication>
#include <QColor>
#include <QStyle>
#include <QStyleHints>

using namespace Qt::StringLiterals;

namespace h2open {

namespace {

/// The choice made with setColorScheme(); `Unknown` follows the system.
Qt::ColorScheme &chosenScheme()
{
    static Qt::ColorScheme scheme = Qt::ColorScheme::Dark;
    return scheme;
}

/// Dark or light, after resolving "follow the system".
bool wantsDark()
{
    const Qt::ColorScheme chosen = chosenScheme();
    if (chosen == Qt::ColorScheme::Unknown) {
        return QGuiApplication::styleHints()->colorScheme() == Qt::ColorScheme::Dark;
    }
    return chosen == Qt::ColorScheme::Dark;
}

void applyPalette()
{
    QApplication::setPalette(wantsDark() ? darkPalette()
                                         : QApplication::style()->standardPalette());
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

void setUpAppearance()
{
    QApplication::setStyle(u"Fusion"_s);
    // When the system switches between light and dark, follow it if asked to.
    QObject::connect(QGuiApplication::styleHints(), &QStyleHints::colorSchemeChanged, qApp, [] {
        if (chosenScheme() == Qt::ColorScheme::Unknown) {
            applyPalette();
        }
    });
    setColorScheme(chosenScheme());
}

void setColorScheme(Qt::ColorScheme scheme)
{
    chosenScheme() = scheme;
    // Title bars and other system-drawn parts; `Unknown` gives it back to the
    // system.
    QGuiApplication::styleHints()->setColorScheme(scheme);
    applyPalette();
}

Qt::ColorScheme colorScheme()
{
    return chosenScheme();
}

void reapplyColorScheme()
{
    applyPalette();
}

} // namespace h2open
