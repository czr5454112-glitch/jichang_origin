#include "ics_core/io/incremental_sha256.hpp"
#include "ics_core/io/canonical_map2_reader.hpp"
#include <iostream>
#include <iterator>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

int main(int argc, char** argv) {
#ifdef _WIN32
  if (_setmode(_fileno(stdin), _O_BINARY) == -1) return 6;
#endif
  if (argc != 2) return 2;
  const auto chunk = std::stoull(argv[1]);
  if (!chunk) return 3;
  const std::string data(std::istreambuf_iterator<char>(std::cin), {});
  czr005::ics::IncrementalSha256 hash;
  static_assert(sizeof(hash) <= 256, "hash storage must not grow with message size");
  for (std::size_t at = 0; at < data.size(); at += chunk) {
    hash.update({});
    hash.update(std::string_view(data).substr(at, std::min<std::size_t>(chunk, data.size()-at)));
  }
  const auto first = hash.hex_digest();
  if (first != hash.hex_digest()) return 4;
  auto fork = hash;
  fork.update("X");
  std::cout << first << '\n' << fork.hex_digest() << '\n';
  if (hash.hex_digest() != first) return 5;
  hash.update("Y");
  std::cout << hash.hex_digest() << '\n'
            << czr005::ics::canonical_map2_detail::sha256_hex(data) << '\n';
}
