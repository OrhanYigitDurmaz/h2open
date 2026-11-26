// Owning QObjects that have no parent.
#pragma once

#include <QCoreApplication>
#include <QObject>
#include <QThread>

#include <memory>

namespace h2open {

/// Deletes a QObject safely even from inside one of its own signals: with
/// deleteLater() while the event loop runs, at once when it does not (then
/// deleteLater() would never run).
struct DeleteLater {
    void operator()(QObject *object) const
    {
        if (QThread::currentThread()->loopLevel() > 0) {
            object->deleteLater();
        } else {
            delete object;
        }
    }
};

/// An owned, parentless QObject, such as a top-level window.
///
/// QObjects are either owned by their parent or by one of these, never both.
template <typename T> using QObjectPtr = std::unique_ptr<T, DeleteLater>;

} // namespace h2open
