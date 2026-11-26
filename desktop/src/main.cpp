// h2open desktop app: the POS for Windows and Linux.
#include "appearance.h"
#include "desktopapp.h"

#include <QApplication>
#include <QLocale>
#include <QSettings>

using namespace Qt::StringLiterals;

int main(int argc, char *argv[])
{
    const QApplication app(argc, argv);
    QApplication::setApplicationName(u"h2open"_s);
    QApplication::setOrganizationName(u"h2open"_s);
    // Settings in an INI file on every platform, not the Windows registry:
    // %APPDATA%\h2open\h2open.ini on Windows, ~/.config/h2open/h2open.ini on
    // Linux. Easy to read, copy or delete.
    QSettings::setDefaultFormat(QSettings::IniFormat);
    // Turkish dates and numbers: month and day names in the calendar,
    // "26.11.2026", "1.234,50".
    QLocale::setDefault(QLocale(QLocale::Turkish, QLocale::Turkey));
    // Fusion, and the theme the user chose last time (dark at first).
    h2open::Appearance::setUp();

    h2open::DesktopApp desktop;
    desktop.start();
    return QApplication::exec();
}
