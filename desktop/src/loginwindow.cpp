#include "loginwindow.h"

#include "dimlabel.h"

#include <QCloseEvent>
#include <QFrame>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>

using namespace Qt::StringLiterals;

namespace h2open {

namespace {

QLabel *label(const QString &text, int pointSize, bool bold, QWidget *parent)
{
    auto *label = new QLabel(text, parent);
    QFont font = label->font();
    font.setPointSize(pointSize);
    font.setBold(bold);
    label->setFont(font);
    return label;
}

} // namespace

LoginWindow::LoginWindow(QWidget *parent)
    : QWidget(parent), m_username(new QLineEdit(this)), m_password(new QLineEdit(this)),
      m_error(new QLabel(this)), m_submit(new QPushButton(u"Log in"_s, this))
{
    setWindowTitle(u"Log in · h2open"_s);
    // Fixed size: the window cannot be resized or maximised.
    setFixedSize(800, 600);

    auto *card = new QFrame(this);
    card->setFrameShape(QFrame::StyledPanel);
    card->setFixedWidth(360);

    auto *brand = label(u"h2open"_s, 10, true, card);
    brand->setForegroundRole(QPalette::Highlight);
    auto *hint = new DimLabel(u"Use the account your admin gave you."_s, card);

    // Names for tests (and accessibility tools) to find the parts by.
    m_username->setObjectName(u"username"_s);
    m_password->setObjectName(u"password"_s);
    m_error->setObjectName(u"error"_s);
    m_submit->setObjectName(u"submit"_s);
    m_password->setEchoMode(QLineEdit::Password);
    m_error->setWordWrap(true);
    m_error->setStyleSheet(u"color: #d92d20;"_s);
    m_error->hide();
    m_submit->setDefault(true);

    auto *layout = new QVBoxLayout(card);
    layout->setContentsMargins(24, 24, 24, 24);
    layout->setSpacing(6);
    layout->addWidget(brand);
    layout->addWidget(label(u"Log in"_s, 18, true, card));
    layout->addWidget(hint);
    layout->addSpacing(12);
    layout->addWidget(label(u"Username"_s, 10, false, card));
    layout->addWidget(m_username);
    layout->addSpacing(8);
    layout->addWidget(label(u"Password"_s, 10, false, card));
    layout->addWidget(m_password);
    layout->addSpacing(8);
    layout->addWidget(m_error);
    layout->addWidget(m_submit);

    auto *outer = new QVBoxLayout(this);
    outer->addWidget(card, 0, Qt::AlignCenter);

    connect(m_username, &QLineEdit::returnPressed, m_password, [this] { m_password->setFocus(); });
    connect(m_password, &QLineEdit::returnPressed, this, &LoginWindow::submit);
    connect(m_submit, &QPushButton::clicked, this, &LoginWindow::submit);
    m_username->setFocus();
}

void LoginWindow::setBusy(bool busy)
{
    m_username->setEnabled(!busy);
    m_password->setEnabled(!busy);
    m_submit->setEnabled(!busy);
    m_submit->setText(busy ? u"Logging in…"_s : u"Log in"_s);
}

void LoginWindow::showError(const QString &message)
{
    setBusy(false);
    m_error->setText(message);
    m_error->show();
    m_password->clear();
    m_password->setFocus();
}

void LoginWindow::clearForm()
{
    setBusy(false);
    m_error->hide();
    m_password->clear();
    m_password->setFocus();
}

void LoginWindow::submit()
{
    if (!m_submit->isEnabled()) {
        return;
    }
    const QString username = m_username->text().trimmed();
    if (username.isEmpty() || m_password->text().isEmpty()) {
        m_error->setText(u"Enter your username and password."_s);
        m_error->show();
        return;
    }
    m_error->hide();
    setBusy(true);
    emit submitted(username, m_password->text());
}

void LoginWindow::closeEvent(QCloseEvent *event)
{
    emit closed();
    event->accept();
}

} // namespace h2open
