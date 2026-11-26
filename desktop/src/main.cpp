// h2open desktop app: the POS for Windows and Linux.
#include "appearance.h"
#include "desktopapp.h"

#include <QApplication>
#include <QLocale>

using namespace Qt::StringLiterals;

int main(int argc, char *argv[])
{
    const QApplication app(argc, argv);
    QApplication::setApplicationName(u"h2open"_s);
    QApplication::setOrganizationName(u"h2open"_s);
    // Turkish dates and numbers: month and day names in the calendar,
    // "26.11.2026", "1.234,50".
    QLocale::setDefault(QLocale(QLocale::Turkish, QLocale::Turkey));
    // Fusion and the h2open dark palette.
    h2open::setUpAppearance();

    h2open::DesktopApp desktop;
    desktop.start();
    return QApplication::exec();
}
