#include "dimlabel.h"

#include <QApplication>
#include <QEvent>

namespace h2open {

namespace {

/// How much of the text colour is kept; the rest is the background.
constexpr float textShare = 0.55F;

QColor mix(const QColor &text, const QColor &background)
{
    const auto channel = [](float a, float b) {
        return (a * textShare) + (b * (1.0F - textShare));
    };
    return QColor::fromRgbF(channel(text.redF(), background.redF()),
                            channel(text.greenF(), background.greenF()),
                            channel(text.blueF(), background.blueF()));
}

} // namespace

DimLabel::DimLabel(const QString &text, QWidget *parent) : QLabel(text, parent)
{
    setWordWrap(true);
    updateColour();
}

void DimLabel::changeEvent(QEvent *event)
{
    QLabel::changeEvent(event);
    if (event->type() == QEvent::PaletteChange || event->type() == QEvent::StyleChange) {
        updateColour();
    }
}

void DimLabel::updateColour()
{
    // Setting the palette sends another PaletteChange.
    if (m_updating) {
        return;
    }
    m_updating = true;
    // From the application palette, not our own: ours holds the last mix.
    const QPalette base = QApplication::palette(this);
    QPalette palette = this->palette();
    palette.setColor(QPalette::WindowText,
                     mix(base.color(QPalette::WindowText), base.color(QPalette::Window)));
    setPalette(palette);
    m_updating = false;
}

} // namespace h2open
