// How the app looks: the Fusion style, the h2open colour palettes, and the
// user's saved choice between them.
#pragma once

#include <QObject>
#include <QPalette>
#include <QString>
#include <QStringView>

#include <optional>

class QMenu;
class QWidget;

namespace h2open {

/// The h2open dark palette: near-black surfaces, white text, and subtle
/// blue button text and highlights, so buttons read as clickable.
[[nodiscard]] QPalette darkPalette();

/// How a colour scheme is saved: "dark", "light" or "system" (`Unknown`).
[[nodiscard]] QString schemeName(Qt::ColorScheme scheme);
/// The scheme saved as `name`; nothing for anything else.
[[nodiscard]] std::optional<Qt::ColorScheme> schemeFromName(QStringView name);

/// The app's colour scheme: dark (the default), light, or whichever of the
/// two the system uses. The choice is saved and used on the next start.
class Appearance : public QObject {
    Q_OBJECT

public:
    /// Use the Fusion style (the one style that follows a palette exactly,
    /// the same on every platform) and the saved scheme. Call once from
    /// main(), after the application and organisation names are set.
    static void setUp();

    /// The one instance, owned by the application.
    [[nodiscard]] static Appearance &instance();

    [[nodiscard]] Qt::ColorScheme colorScheme() const { return m_scheme; }

    /// Apply, save and announce a scheme. The system is told too, so
    /// window title bars match.
    void setColorScheme(Qt::ColorScheme scheme);

    /// Apply the palette again, e.g. after QApplication::setStyle(), which
    /// resets it.
    void reapply() const;

signals:
    void colorSchemeChanged(Qt::ColorScheme scheme);

private:
    explicit Appearance(QObject *parent);

    Qt::ColorScheme m_scheme = Qt::ColorScheme::Dark;
};

/// A "Theme" menu (Dark / Light / System) that shows and changes the
/// scheme, and stays in step when it is changed elsewhere.
[[nodiscard]] QMenu *createThemeMenu(QWidget *parent);

} // namespace h2open
