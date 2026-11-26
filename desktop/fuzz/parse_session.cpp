// libFuzzer harness: parseSession reads whatever the network sends.
//
//   cmake --preset fuzz && cmake --build --preset fuzz
//   ./build/fuzz/fuzz_parse_session -max_total_time=60
#include "api.h"

#include <QByteArray>

#include <cstddef>
#include <cstdint>
#include <cstdlib>

// libFuzzer hands over a C buffer: this is the one place it is turned into a
// bounds-checked Qt type.
#pragma clang unsafe_buffer_usage begin
extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t *data, std::size_t size)
{
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast): libFuzzer's C buffer.
    const auto *bytes = reinterpret_cast<const char *>(data);
    const QByteArray body = QByteArray::fromRawData(bytes, static_cast<qsizetype>(size));
#pragma clang unsafe_buffer_usage end
    const auto session = h2open::parseSession(body);
    // A login result always has a token and a username.
    if (session && (session->token.isEmpty() || session->user.username.isEmpty())) {
        std::abort();
    }
    return 0;
}
