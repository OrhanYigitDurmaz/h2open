#include "gallery.h"

#include "appearance.h"
#include "dimlabel.h"

#include <QApplication>
#include <QButtonGroup>
#include <QCalendarWidget>
#include <QCheckBox>
#include <QColorDialog>
#include <QComboBox>
#include <QCommandLinkButton>
#include <QCompleter>
#include <QDateEdit>
#include <QDateTimeEdit>
#include <QDial>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
#include <QFileDialog>
#include <QFontComboBox>
#include <QFontDialog>
#include <QFormLayout>
#include <QFrame>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QInputDialog>
#include <QIntValidator>
#include <QKeySequenceEdit>
#include <QLCDNumber>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMdiArea>
#include <QMdiSubWindow>
#include <QMenu>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QProgressBar>
#include <QPushButton>
#include <QRadioButton>
#include <QScrollBar>
#include <QSlider>
#include <QSpinBox>
#include <QSplitter>
#include <QStackedWidget>
#include <QStyleFactory>
#include <QStyleHints>
#include <QTabWidget>
#include <QTableWidget>
#include <QTextEdit>
#include <QTimeEdit>
#include <QToolBox>
#include <QToolButton>
#include <QTreeWidget>
#include <QVBoxLayout>

#include <array>
#include <utility>

using namespace Qt::StringLiterals;

namespace h2open {

namespace {

/// Cards per row.
constexpr int columns = 4;

const QStringList &products()
{
    static const QStringList list{
        u"19 L carboy"_s,
        u"10 L carboy"_s,
        u"5 L bottle"_s,
        u"0.5 L pack of 12"_s,
    };
    return list;
}

struct Customer {
    QString name;
    QString address;
    int carboys;
};

const std::array<Customer, 4> &customers()
{
    static const std::array<Customer, 4> list{
        Customer{.name = u"Ayşe Yılmaz"_s, .address = u"Atatürk Cd. 12"_s, .carboys = 2},
        Customer{.name = u"Mehmet Demir"_s, .address = u"Cumhuriyet Sk. 4"_s, .carboys = 1},
        Customer{.name = u"Zeynep Kaya"_s, .address = u"İnönü Blv. 30"_s, .carboys = 3},
        Customer{.name = u"Ali Çelik"_s, .address = u"Gazi Cd. 7"_s, .carboys = 0},
    };
    return list;
}

/// A box titled with the widget's class names, laid out top to bottom.
QGroupBox *card(const QString &title, QWidget *parent)
{
    auto *box = new QGroupBox(title, parent);
    auto *layout = new QVBoxLayout(box);
    layout->setAlignment(Qt::AlignTop);
    return box;
}

QVBoxLayout *layoutOf(const QGroupBox *box)
{
    return qobject_cast<QVBoxLayout *>(box->layout());
}

QLabel *caption(const QString &text, QWidget *parent)
{
    return new DimLabel(text, parent);
}

} // namespace

Gallery::Gallery(QWidget *parent) : QWidget(parent), m_cards(new QWidget(this))
{
    auto *grid = new QGridLayout(m_cards);
    grid->setSpacing(16);
    const std::array cards{
        buttons(),  toggles(), lineEdits(),   comboBoxes(), numbers(), dates(),
        calendar(), ranges(),  textEditors(), labels(),     list(),    tree(),
        table(),    tabs(),    containers(),  dialogs(),
    };
    for (int i = 0; std::cmp_less(i, cards.size()); ++i) {
        grid->addWidget(cards.at(static_cast<std::size_t>(i)), i / columns, i % columns);
    }
    for (int column = 0; column < columns; ++column) {
        grid->setColumnStretch(column, 1);
    }

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(24, 24, 24, 24);
    layout->setSpacing(24);
    layout->addWidget(header());
    layout->addWidget(m_cards);
    layout->addStretch();
}

QWidget *Gallery::header()
{
    auto *header = new QWidget(this);
    auto *title = new QLabel(u"<h2>Widget gallery</h2>"_s, header);
    auto *subtitle =
        caption(u"Every Qt Widgets widget. Dates and numbers use the Turkish locale."_s, header);

    auto *style = new QComboBox(header);
    style->addItems(QStyleFactory::keys());
    // The style reports its name in lower case ("fusion"); the list says "Fusion".
    style->setCurrentIndex(style->findText(QApplication::style()->name(), Qt::MatchFixedString));
    connect(style, &QComboBox::currentTextChanged, this, [](const QString &name) {
        QApplication::setStyle(name);
        // A new style resets the palette.
        reapplyColorScheme();
    });

    auto *scheme = new QComboBox(header);
    scheme->addItem(u"Dark"_s, QVariant::fromValue(Qt::ColorScheme::Dark));
    scheme->addItem(u"Light"_s, QVariant::fromValue(Qt::ColorScheme::Light));
    scheme->addItem(u"System"_s, QVariant::fromValue(Qt::ColorScheme::Unknown));
    scheme->setCurrentIndex(scheme->findData(QVariant::fromValue(colorScheme())));
    connect(scheme, &QComboBox::currentIndexChanged, this,
            [scheme](int) { setColorScheme(scheme->currentData().value<Qt::ColorScheme>()); });

    auto *enabled = new QCheckBox(u"Widgets enabled"_s, header);
    enabled->setChecked(true);
    connect(enabled, &QCheckBox::toggled, m_cards, &QWidget::setEnabled);

    auto *text = new QVBoxLayout();
    text->addWidget(title);
    text->addWidget(subtitle);

    auto *layout = new QHBoxLayout(header);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->addLayout(text);
    layout->addStretch();
    layout->addWidget(new QLabel(u"Style"_s, header));
    layout->addWidget(style);
    layout->addWidget(new QLabel(u"Colours"_s, header));
    layout->addWidget(scheme);
    layout->addWidget(enabled);
    return header;
}

QGroupBox *Gallery::buttons()
{
    auto *box = card(u"QPushButton · QToolButton · QCommandLinkButton"_s, m_cards);
    auto *layout = layoutOf(box);

    auto *row = new QHBoxLayout();
    auto *primary = new QPushButton(u"Default"_s, box);
    primary->setDefault(true);
    row->addWidget(primary);
    row->addWidget(new QPushButton(u"Normal"_s, box));
    auto *disabled = new QPushButton(u"Disabled"_s, box);
    disabled->setEnabled(false);
    row->addWidget(disabled);
    layout->addLayout(row);

    auto *second = new QHBoxLayout();
    auto *checkable = new QPushButton(u"Checkable"_s, box);
    checkable->setCheckable(true);
    checkable->setChecked(true);
    second->addWidget(checkable);
    auto *flat = new QPushButton(u"Flat"_s, box);
    flat->setFlat(true);
    second->addWidget(flat);
    auto *withMenu = new QPushButton(u"With menu"_s, box);
    auto *menu = new QMenu(withMenu);
    menu->addAction(u"New order"_s);
    menu->addAction(u"New customer"_s);
    withMenu->setMenu(menu);
    second->addWidget(withMenu);
    layout->addLayout(second);

    auto *tool = new QToolButton(box);
    tool->setText(u"Tool button"_s);
    tool->setPopupMode(QToolButton::MenuButtonPopup);
    tool->setMenu(menu);
    layout->addWidget(tool);

    layout->addWidget(
        new QCommandLinkButton(u"Command link"_s, u"A big button with a description."_s, box));
    return box;
}

QGroupBox *Gallery::toggles()
{
    auto *box = card(u"QCheckBox · QRadioButton"_s, m_cards);
    auto *layout = layoutOf(box);
    auto *checked = new QCheckBox(u"Checked"_s, box);
    checked->setChecked(true);
    layout->addWidget(checked);
    layout->addWidget(new QCheckBox(u"Unchecked"_s, box));
    auto *tristate = new QCheckBox(u"Tristate: partly"_s, box);
    tristate->setTristate(true);
    tristate->setCheckState(Qt::PartiallyChecked);
    layout->addWidget(tristate);

    auto *group = new QButtonGroup(box);
    for (const QString &label : {u"Delivery"_s, u"Walk-in"_s, u"Pickup"_s}) {
        auto *radio = new QRadioButton(label, box);
        group->addButton(radio);
        layout->addWidget(radio);
    }
    group->buttons().constFirst()->setChecked(true);
    return box;
}

QGroupBox *Gallery::lineEdits()
{
    auto *box = card(u"QLineEdit"_s, m_cards);
    auto *form = new QFormLayout();
    auto *plain = new QLineEdit(box);
    plain->setPlaceholderText(u"Placeholder"_s);
    plain->setClearButtonEnabled(true);
    form->addRow(u"Text"_s, plain);

    auto *password = new QLineEdit(u"secret"_s, box);
    password->setEchoMode(QLineEdit::Password);
    form->addRow(u"Password"_s, password);

    auto *phone = new QLineEdit(box);
    phone->setInputMask(u"(999) 999 99 99;_"_s);
    form->addRow(u"Input mask"_s, phone);

    auto *number = new QLineEdit(box);
    number->setValidator(new QIntValidator(0, 999, number));
    number->setPlaceholderText(u"0–999 only"_s);
    form->addRow(u"Validator"_s, number);

    auto *completing = new QLineEdit(box);
    auto *completer = new QCompleter(products(), completing);
    completer->setCaseSensitivity(Qt::CaseInsensitive);
    completing->setCompleter(completer);
    completing->setPlaceholderText(u"Type “car”"_s);
    form->addRow(u"Completer"_s, completing);

    layoutOf(box)->addLayout(form);
    return box;
}

QGroupBox *Gallery::comboBoxes()
{
    auto *box = card(u"QComboBox · QFontComboBox"_s, m_cards);
    auto *layout = layoutOf(box);
    auto *fixed = new QComboBox(box);
    fixed->addItems(products());
    layout->addWidget(fixed);
    auto *editable = new QComboBox(box);
    editable->setEditable(true);
    editable->addItems(products());
    editable->setCurrentText(u"Editable: type anything"_s);
    layout->addWidget(editable);
    layout->addWidget(new QFontComboBox(box));
    return box;
}

QGroupBox *Gallery::numbers()
{
    auto *box = card(u"QSpinBox · QDoubleSpinBox"_s, m_cards);
    auto *form = new QFormLayout();
    auto *quantity = new QSpinBox(box);
    quantity->setRange(0, 100);
    quantity->setValue(3);
    quantity->setSuffix(u" adet"_s);
    form->addRow(u"Quantity"_s, quantity);

    auto *price = new QDoubleSpinBox(box);
    price->setRange(0, 100000);
    price->setDecimals(2);
    price->setValue(1234.5);
    price->setPrefix(u"₺ "_s);
    price->setGroupSeparatorShown(true);
    form->addRow(u"Price"_s, price);

    layoutOf(box)->addLayout(form);
    layoutOf(box)->addWidget(caption(u"Turkish locale: comma for decimals."_s, box));
    return box;
}

QGroupBox *Gallery::dates()
{
    auto *box = card(u"QDateEdit · QTimeEdit · QDateTimeEdit"_s, m_cards);
    auto *form = new QFormLayout();
    auto *date = new QDateEdit(QDate::currentDate(), box);
    date->setCalendarPopup(true);
    form->addRow(u"Date"_s, date);

    auto *time = new QTimeEdit(QTime::currentTime(), box);
    form->addRow(u"Time"_s, time);

    auto *both = new QDateTimeEdit(QDateTime::currentDateTime(), box);
    both->setCalendarPopup(true);
    form->addRow(u"Both"_s, both);
    layoutOf(box)->addLayout(form);

    auto *picked = caption(QString(), box);
    const auto show = [picked](QDate value) {
        picked->setText(QLocale().toString(value, QLocale::LongFormat));
    };
    show(date->date());
    connect(date, &QDateEdit::dateChanged, picked, show);
    layoutOf(box)->addWidget(picked);
    return box;
}

QGroupBox *Gallery::calendar()
{
    auto *box = card(u"QCalendarWidget"_s, m_cards);
    auto *calendar = new QCalendarWidget(box);
    calendar->setGridVisible(true);
    layoutOf(box)->addWidget(calendar);
    return box;
}

QGroupBox *Gallery::ranges()
{
    auto *box = card(u"QSlider · QDial · QScrollBar · QProgressBar · QLCDNumber"_s, m_cards);
    auto *layout = layoutOf(box);

    auto *slider = new QSlider(Qt::Horizontal, box);
    slider->setRange(0, 100);
    slider->setValue(40);
    slider->setTickPosition(QSlider::TicksBelow);
    layout->addWidget(slider);

    auto *scroll = new QScrollBar(Qt::Horizontal, box);
    scroll->setRange(0, 100);
    layout->addWidget(scroll);

    auto *progress = new QProgressBar(box);
    layout->addWidget(progress);

    auto *row = new QHBoxLayout();
    auto *dial = new QDial(box);
    dial->setRange(0, 100);
    dial->setNotchesVisible(true);
    dial->setFixedSize(80, 80);
    row->addWidget(dial);
    auto *lcd = new QLCDNumber(3, box);
    lcd->setSegmentStyle(QLCDNumber::Flat);
    row->addWidget(lcd);
    layout->addLayout(row);
    layout->addWidget(caption(u"All five move together."_s, box));

    // Each control drives the others.
    const std::array<QAbstractSlider *, 3> controls{slider, scroll, dial};
    for (const QAbstractSlider *source : controls) {
        connect(source, &QAbstractSlider::valueChanged, progress, &QProgressBar::setValue);
        connect(source, &QAbstractSlider::valueChanged, lcd, qOverload<int>(&QLCDNumber::display));
        for (const QAbstractSlider *target : controls) {
            if (target != source) {
                connect(source, &QAbstractSlider::valueChanged, target, &QAbstractSlider::setValue);
            }
        }
    }
    progress->setValue(slider->value());
    lcd->display(slider->value());
    scroll->setValue(slider->value());
    dial->setValue(slider->value());
    return box;
}

QGroupBox *Gallery::textEditors()
{
    auto *box = card(u"QTextEdit · QPlainTextEdit"_s, m_cards);
    auto *rich = new QTextEdit(box);
    rich->setHtml(u"<b>Rich text</b> with <i>styles</i>, <span style='color:#3b82f6'>colour"
                  "</span> and lists:<ul><li>19 L carboys</li><li>deposits</li></ul>"_s);
    rich->setFixedHeight(110);
    layoutOf(box)->addWidget(rich);
    auto *plain = new QPlainTextEdit(u"Plain text.\nDelivery notes would go here."_s, box);
    plain->setFixedHeight(70);
    layoutOf(box)->addWidget(plain);
    return box;
}

QGroupBox *Gallery::labels()
{
    auto *box = card(u"QLabel · QKeySequenceEdit"_s, m_cards);
    auto *layout = layoutOf(box);
    layout->addWidget(new QLabel(u"Plain label"_s, box));
    layout->addWidget(
        new QLabel(u"<b>Rich</b> <i>label</i> with <u>HTML</u> and ₺1.234,50"_s, box));
    auto *link = new QLabel(u"<a href='https://doc.qt.io'>A link to the Qt docs</a>"_s, box);
    link->setOpenExternalLinks(true);
    layout->addWidget(link);
    auto *line = new QFrame(box);
    line->setFrameShape(QFrame::HLine);
    layout->addWidget(line);
    layout->addWidget(caption(u"Press a shortcut:"_s, box));
    layout->addWidget(new QKeySequenceEdit(QKeySequence(u"Ctrl+N"_s), box));
    return box;
}

QGroupBox *Gallery::list()
{
    auto *box = card(u"QListWidget"_s, m_cards);
    auto *list = new QListWidget(box);
    for (const Customer &customer : customers()) {
        auto *item = new QListWidgetItem(customer.name, list);
        item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
        item->setCheckState(customer.carboys > 0 ? Qt::Checked : Qt::Unchecked);
    }
    list->setFixedHeight(130);
    layoutOf(box)->addWidget(list);
    layoutOf(box)->addWidget(caption(u"Checked: has carboys out."_s, box));
    return box;
}

QGroupBox *Gallery::tree()
{
    auto *box = card(u"QTreeWidget"_s, m_cards);
    auto *tree = new QTreeWidget(box);
    tree->setHeaderLabels({u"Customer"_s, u"Carboys"_s});
    for (const Customer &customer : customers()) {
        auto *top = new QTreeWidgetItem(tree, {customer.name, QString::number(customer.carboys)});
        new QTreeWidgetItem(top, {customer.address});
    }
    tree->expandToDepth(0);
    tree->setFixedHeight(160);
    layoutOf(box)->addWidget(tree);
    return box;
}

QGroupBox *Gallery::table()
{
    auto *box = card(u"QTableWidget"_s, m_cards);
    const auto &rows = customers();
    auto *table = new QTableWidget(static_cast<int>(rows.size()), 3, box);
    table->setHorizontalHeaderLabels({u"Customer"_s, u"Address"_s, u"Out"_s});
    for (int row = 0; std::cmp_less(row, rows.size()); ++row) {
        const Customer &customer = rows.at(static_cast<std::size_t>(row));
        table->setItem(row, 0, new QTableWidgetItem(customer.name));
        table->setItem(row, 1, new QTableWidgetItem(customer.address));
        auto *count = new QTableWidgetItem();
        count->setData(Qt::DisplayRole, customer.carboys);
        table->setItem(row, 2, count);
    }
    table->setSortingEnabled(true);
    table->horizontalHeader()->setStretchLastSection(true);
    table->resizeColumnsToContents();
    table->setFixedHeight(160);
    layoutOf(box)->addWidget(table);
    layoutOf(box)->addWidget(caption(u"Click a header to sort."_s, box));
    return box;
}

QGroupBox *Gallery::tabs()
{
    auto *box = card(u"QTabWidget · QToolBox"_s, m_cards);
    auto *tabs = new QTabWidget(box);
    for (const QString &name : {u"Orders"_s, u"Customers"_s, u"Containers"_s}) {
        tabs->addTab(new QLabel(u"Content of %1."_s.arg(name), tabs), name);
    }
    tabs->setFixedHeight(90);
    layoutOf(box)->addWidget(tabs);

    auto *toolbox = new QToolBox(box);
    toolbox->addItem(new QLabel(u"First page"_s, toolbox), u"Today"_s);
    toolbox->addItem(new QLabel(u"Second page"_s, toolbox), u"This week"_s);
    toolbox->setFixedHeight(130);
    layoutOf(box)->addWidget(toolbox);
    return box;
}

QGroupBox *Gallery::containers()
{
    auto *box = card(u"QStackedWidget · QSplitter · QMdiArea · QGroupBox"_s, m_cards);
    auto *layout = layoutOf(box);

    auto *pages = new QComboBox(box);
    auto *stack = new QStackedWidget(box);
    for (const QString &name : {u"Page one"_s, u"Page two"_s, u"Page three"_s}) {
        pages->addItem(name);
        stack->addWidget(new QLabel(u"Stacked: %1"_s.arg(name), stack));
    }
    connect(pages, &QComboBox::currentIndexChanged, stack, &QStackedWidget::setCurrentIndex);
    layout->addWidget(pages);
    layout->addWidget(stack);

    auto *splitter = new QSplitter(box);
    splitter->addWidget(new QLabel(u"Drag the"_s, splitter));
    splitter->addWidget(new QLabel(u"divider"_s, splitter));
    splitter->setFixedHeight(30);
    layout->addWidget(splitter);

    auto *mdi = new QMdiArea(box);
    mdi->addSubWindow(new QLabel(u"Window A"_s))->resize(120, 60);
    mdi->addSubWindow(new QLabel(u"Window B"_s))->resize(120, 60);
    mdi->tileSubWindows();
    mdi->setFixedHeight(110);
    layout->addWidget(mdi);

    auto *checkable = new QGroupBox(u"Checkable group box"_s, box);
    checkable->setCheckable(true);
    auto *inner = new QVBoxLayout(checkable);
    inner->addWidget(new QLabel(u"Untick to disable me."_s, checkable));
    layout->addWidget(checkable);
    return box;
}

QGroupBox *Gallery::dialogs()
{
    auto *box = card(u"Dialogs · QDialogButtonBox"_s, m_cards);
    auto *grid = new QGridLayout();
    const auto add = [&](const QString &label, int position, auto open) {
        auto *button = new QPushButton(label, box);
        connect(button, &QPushButton::clicked, box, open);
        grid->addWidget(button, position / 2, position % 2);
    };
    add(u"QMessageBox"_s, 0,
        [box] { QMessageBox::information(box, u"h2open"_s, u"A message box."_s); });
    add(u"QInputDialog"_s, 1,
        [box] { QInputDialog::getText(box, u"h2open"_s, u"Customer name:"_s); });
    add(u"QColorDialog"_s, 2, [box] { QColorDialog::getColor(Qt::blue, box); });
    add(u"QFontDialog"_s, 3, [box] {
        bool ok = false;
        QFontDialog::getFont(&ok, box);
    });
    add(u"QFileDialog"_s, 4, [box] { QFileDialog::getOpenFileName(box); });
    add(u"About Qt"_s, 5, [box] { QMessageBox::aboutQt(box); });
    layoutOf(box)->addLayout(grid);

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel |
                                             QDialogButtonBox::Apply | QDialogButtonBox::Help,
                                         box);
    layoutOf(box)->addWidget(buttons);
    return box;
}

} // namespace h2open
