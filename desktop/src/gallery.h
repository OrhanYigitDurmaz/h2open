// Every Qt Widgets widget, one box each, with the style and colour scheme
// switchable at the top. Shown after login until real screens replace it.
#pragma once

#include <QWidget>

class QGroupBox;

namespace h2open {

class Gallery : public QWidget {
    Q_OBJECT

public:
    explicit Gallery(QWidget *parent = nullptr);

private:
    QWidget *header();
    QGroupBox *buttons();
    QGroupBox *toggles();
    QGroupBox *lineEdits();
    QGroupBox *comboBoxes();
    QGroupBox *numbers();
    QGroupBox *dates();
    QGroupBox *calendar();
    QGroupBox *ranges();
    QGroupBox *textEditors();
    QGroupBox *labels();
    QGroupBox *list();
    QGroupBox *tree();
    QGroupBox *table();
    QGroupBox *tabs();
    QGroupBox *containers();
    QGroupBox *dialogs();

    QWidget *m_cards;
};

} // namespace h2open
