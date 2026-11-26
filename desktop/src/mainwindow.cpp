#include "mainwindow.h"

#include "appearance.h"
#include "gallery.h"

#include <QApplication>
#include <QCloseEvent>
#include <QLabel>
#include <QMenuBar>
#include <QScrollArea>
#include <QSizePolicy>
#include <QStatusBar>
#include <QToolBar>

using namespace Qt::StringLiterals;

namespace h2open {

MainWindow::MainWindow(const User &user, QWidget *parent) : QMainWindow(parent)
{
    setWindowTitle(u"h2open"_s);
    resize(1280, 800);
    setMinimumSize(800, 600);

    auto *logout = new QAction(u"Log out"_s, this);
    connect(logout, &QAction::triggered, this, &MainWindow::logoutRequested);

    auto *fileMenu = menuBar()->addMenu(u"&File"_s);
    fileMenu->addAction(logout);
    fileMenu->addSeparator();
    fileMenu->addAction(u"&Quit"_s, QKeySequence::Quit, this, &QWidget::close);
    menuBar()->addMenu(u"&View"_s)->addMenu(createThemeMenu(this));
    menuBar()->addMenu(u"&Help"_s)->addAction(u"About &Qt"_s, qApp, &QApplication::aboutQt);

    auto *toolbar = addToolBar(u"Account"_s);
    toolbar->setMovable(false);
    auto *brand = new QLabel(u"<b>h2open</b>"_s, toolbar);
    brand->setContentsMargins(8, 0, 8, 0);
    toolbar->addWidget(brand);
    auto *spacer = new QWidget(toolbar);
    spacer->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    toolbar->addWidget(spacer);
    auto *who = new QLabel(u"%1 (%2)"_s.arg(user.name, user.username), toolbar);
    who->setContentsMargins(8, 0, 8, 0);
    toolbar->addWidget(who);
    toolbar->addAction(logout);

    statusBar()->showMessage(u"Logged in as %1."_s.arg(user.username));

    // Screens replace the gallery as they are built.
    auto *scroll = new QScrollArea(this);
    scroll->setWidgetResizable(true);
    scroll->setWidget(new Gallery(scroll));
    setCentralWidget(scroll);
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    emit closed();
    event->accept();
}

} // namespace h2open
