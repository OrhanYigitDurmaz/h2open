// The application, opened maximised after a successful login.
#pragma once

#include "api.h"

#include <QMainWindow>

namespace h2open {

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    explicit MainWindow(const User &user, QWidget *parent = nullptr);

signals:
    void logoutRequested();
    /// The user closed the window (not a logout).
    void closed();

protected:
    void closeEvent(QCloseEvent *event) override;
};

} // namespace h2open
