// A label in a dimmer colour, for hints and captions.
#pragma once

#include <QLabel>

namespace h2open {

/// Text halfway between the normal text and the background colour.
///
/// The palette's own PlaceholderText colour cannot be used: some desktop
/// palettes make it the same as the background, hiding the text.
class DimLabel : public QLabel {
    Q_OBJECT

public:
    explicit DimLabel(const QString &text, QWidget *parent = nullptr);

protected:
    void changeEvent(QEvent *event) override;

private:
    void updateColour();

    bool m_updating = false;
};

} // namespace h2open
