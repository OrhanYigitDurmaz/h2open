// How the app looks: the Fusion style and the h2open colour palettes.
#pragma once

#include <QPalette>

namespace h2open {

/// The h2open dark palette: near-black surfaces, white text, and subtle
/// blue button text and highlights, so buttons read as clickable.
[[nodiscard]] QPalette darkPalette();

/// Use the Fusion style (the one style that follows a palette exactly, the
/// same on every platform) and the dark palette. Call once, from main().
void setUpAppearance();

/// Switch between the dark palette (`Dark`), Fusion's light palette
/// (`Light`) and whichever of the two the system uses (`Unknown`). The
/// system is told too, so window title bars match.
void setColorScheme(Qt::ColorScheme scheme);

/// The scheme last chosen with setColorScheme().
[[nodiscard]] Qt::ColorScheme colorScheme();

/// Apply the chosen scheme again, e.g. after QApplication::setStyle(),
/// which resets the palette.
void reapplyColorScheme();

} // namespace h2open
