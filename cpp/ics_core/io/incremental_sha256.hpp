#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>

namespace czr005::ics {

// SHA-256 with bounded working storage. Compression and canonical bytes match
// canonical_map2_detail::sha256_hex; only buffering/padding are incremental.
// FIPS 180-4 sections 5.1.1, 5.3.3 and 6.2. No whole-message allocation.
class IncrementalSha256 {
 public:
  void update(std::string_view input) {
    constexpr auto limit = std::numeric_limits<std::uint64_t>::max() / 8U;
    if (input.size() > limit - bytes_)
      throw std::length_error("SHA-256 input exceeds the 64-bit bit-length limit");
    bytes_ += static_cast<std::uint64_t>(input.size());
    if (used_) {
      const auto take = std::min(input.size(), block_.size() - used_);
      if (take) std::memcpy(block_.data() + used_, input.data(), take);
      used_ += take;
      input.remove_prefix(take);
      if (used_ == block_.size()) {
        compress(block_.data());
        used_ = 0;
      }
    }
    while (input.size() >= block_.size()) {
      compress(reinterpret_cast<const std::uint8_t*>(input.data()));
      input.remove_prefix(block_.size());
    }
    if (!input.empty()) {
      std::memcpy(block_.data(), input.data(), input.size());
      used_ = input.size();
    }
  }

  // Digest a copy: repeated reads and subsequent updates preserve the stream.
  [[nodiscard]] std::string hex_digest() const {
    auto finished = *this;
    finished.finish();
    static constexpr char digits[] = "0123456789abcdef";
    std::string result;
    result.reserve(64);
    for (const auto word : finished.state_)
      for (int shift = 28; shift >= 0; shift -= 4)
        result.push_back(digits[(word >> shift) & 0x0fU]);
    return result;
  }

 private:
  static std::uint32_t rotate(std::uint32_t v, unsigned n) {
    return (v >> n) | (v << (32U - n));
  }

  void finish() {
    const auto bits = bytes_ * 8U;
    block_[used_++] = 0x80U;
    if (used_ > 56) {
      std::fill(block_.begin() + used_, block_.end(), 0);
      compress(block_.data());
      used_ = 0;
    }
    std::fill(block_.begin() + used_, block_.begin() + 56, 0);
    for (unsigned i = 0; i < 8; ++i)
      block_[56 + i] = static_cast<std::uint8_t>(bits >> (56U - 8U * i));
    compress(block_.data());
  }

  void compress(const std::uint8_t* input) {
    static constexpr std::array<std::uint32_t, 64> constants = {
        0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
        0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
        0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
        0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
        0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
        0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
        0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
        0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
        0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
        0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
        0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
        0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
        0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
        0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
        0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
        0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U};
    std::array<std::uint32_t, 64> words{};
    for (std::size_t i = 0; i < 16; ++i) {
      const auto at = i * 4;
      words[i] = (static_cast<std::uint32_t>(input[at]) << 24U) |
                 (static_cast<std::uint32_t>(input[at + 1]) << 16U) |
                 (static_cast<std::uint32_t>(input[at + 2]) << 8U) |
                  static_cast<std::uint32_t>(input[at + 3]);
    }
    for (std::size_t i = 16; i < words.size(); ++i) {
      const auto s0 = rotate(words[i-15], 7) ^ rotate(words[i-15], 18) ^ (words[i-15] >> 3U);
      const auto s1 = rotate(words[i-2], 17) ^ rotate(words[i-2], 19) ^ (words[i-2] >> 10U);
      words[i] = words[i-16] + s0 + words[i-7] + s1;
    }
    auto a=state_[0], b=state_[1], c=state_[2], d=state_[3];
    auto e=state_[4], f=state_[5], g=state_[6], h=state_[7];
    for (std::size_t i = 0; i < words.size(); ++i) {
      const auto s1 = rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25);
      const auto choose = (e & f) ^ ((~e) & g);
      const auto t1 = h + s1 + choose + constants[i] + words[i];
      const auto s0 = rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22);
      const auto majority = (a & b) ^ (a & c) ^ (b & c);
      const auto t2 = s0 + majority;
      h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    state_[0]+=a; state_[1]+=b; state_[2]+=c; state_[3]+=d;
    state_[4]+=e; state_[5]+=f; state_[6]+=g; state_[7]+=h;
  }

  std::array<std::uint32_t, 8> state_ = {
      0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
      0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U};
  std::array<std::uint8_t, 64> block_{};
  std::size_t used_ = 0;
  std::uint64_t bytes_ = 0;
};

}  // namespace czr005::ics
