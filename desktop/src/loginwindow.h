// The first window: a fixed 800×600 login screen.
#pragma once

#include <QWidget>

class QLabel;
class QLineEdit;
class QPushButton;

namespace h2open {

class LoginWindow : public QWidget {
    Q_OBJECT

public:
    explicit LoginWindow(QWidget *parent = nullptr);

    /// While logging in, nothing can be typed or pressed.
    void setBusy(bool busy);
    /// Show why the login failed, clear the password and focus it.
    void showError(const QString &message);
    /// Ready for the next login: no error, no password.
    void clearForm();

signals:
    void submitted(const QString &username, const QString &password);
    /// The user closed the window.
    void closed();

protected:
    void closeEvent(QCloseEvent *event) override;

private:
    void submit();

    QLineEdit *m_username;
    QLineEdit *m_password;
    QLabel *m_error;
    QPushButton *m_submit;
};

} // namespace h2open
