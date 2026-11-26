# Rules for the h2open desktop app (C++23, Qt 6 Widgets)

These rules hold for all code in `desktop/`. The compiler flags, clang-tidy,
clazy and the sanitizers enforce most of them. Run `/verify desktop`
(or the commands in `.claude/skills/verify/SKILL.md`) after every change.

## Ownership: the main source of Qt bugs

- **Non-QObject types**: values, or `std::unique_ptr`. Never `new`/`delete`
  by hand.
- **QObjects**: owned by **either** their parent (`new QLabel(text, parent)`)
  **or** a `QObjectPtr<T>` (`src/qtmemory.h`) with no parent. Never both.
  Top-level windows have no parent, so they live in a `QObjectPtr`.
- **Non-owning references to QObjects** that may outlive the object:
  `QPointer<T>`, which becomes null when the object is destroyed.
- Never delete a QObject from inside one of its own signals.
  `QObjectPtr::reset()` uses `deleteLater()` for that.

## Types instead of nulls, exceptions and unions

| Rust | C++ here |
|---|---|
| `Result<T, E>` | `std::expected<T, E>`, e.g. `parseSession` |
| `Option<T>` | `std::optional<T>`, always checked before use |
| `enum` with data | `std::variant` and `std::visit` |
| `&[T]`, `&str` | `std::span`, `QSpan`, `QStringView`, `QAnyStringView` |

- Functions that return a result or an error are `[[nodiscard]]`.
- No exceptions for expected failures: network errors, bad input and
  refusals are values (`std::expected`, or a failure signal).
- No raw pointer arithmetic or indexing (`-Wunsafe-buffer-usage`). Data
  from C (`argv`, libFuzzer) becomes a bounds-checked type in one place,
  inside `#pragma clang unsafe_buffer_usage begin/end`.

## Signals and slots

- Always use pointer-to-member syntax: `connect(a, &A::sig, b, &B::slot)`.
  Never `SIGNAL()`/`SLOT()`.
- Always pass a context object to a lambda connect, the object whose
  lifetime the lambda depends on: `connect(a, &A::sig, this, [this] { … })`.
- Pass small, trivially copyable types (such as `LoginFailure`) by value.

## Qt 6 idioms

- Strings always say their encoding: `u"…"_s` with
  `using namespace Qt::StringLiterals;` (`QT_NO_CAST_FROM_ASCII` is on).
- Nothing deprecated up to Qt 6.8. Qt 5 APIs and macros
  (`QT_STRICT_ITERATORS`, `QRegExp`, `qrand`, `QDesktopWidget`…) do not
  exist here.
- Use `Q_OBJECT` in every QObject subclass. Range-for over Qt containers uses a
  `const` container (or `std::as_const`), so it does not detach.

## Logic apart from the UI

- Server calls, parsing and rules live in plain C++/Qt Core
  (`h2open_api`: no widgets). They are unit-tested and run under
  ASan/UBSan/TSan quickly.
- Widgets only show data and turn input into calls. Tests drive them
  through object names (`setObjectName`) with `QT_QPA_PLATFORM=offscreen`.
- Anything that parses data from the network or from files gets a
  libFuzzer harness in `fuzz/`, with seed inputs in `fuzz/corpus/<name>/`.

## Locale

- `main.cpp` sets the Turkish locale. Dates and numbers are shown through
  `QLocale()` (e.g. `QLocale().toString(date, QLocale::LongFormat)`), never
  hand-formatted.
