#pragma once

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "ics_core/graph/graph.hpp"

namespace czr005::ics {

inline constexpr std::string_view kCanonicalMap2NormalizedSha256 =
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63";

namespace canonical_map2_detail {

inline std::string normalize_newlines(std::string_view source) {
  std::string normalized;
  normalized.reserve(source.size());
  for (std::size_t index = 0; index < source.size(); ++index) {
    if (source[index] != '\r') {
      normalized.push_back(source[index]);
      continue;
    }
    normalized.push_back('\n');
    if (index + 1 < source.size() && source[index + 1] == '\n') {
      ++index;
    }
  }
  return normalized;
}

inline std::uint32_t rotate_right(std::uint32_t value, unsigned int count) {
  return (value >> count) | (value << (32U - count));
}

inline std::string sha256_hex(std::string_view source) {
  if (source.size() > std::numeric_limits<std::uint64_t>::max() / 8U) {
    throw std::runtime_error("canonical map2 is too large to hash with SHA-256");
  }

  std::vector<std::uint8_t> message;
  message.reserve(source.size() + 72U);
  for (const char byte : source) {
    message.push_back(static_cast<std::uint8_t>(static_cast<unsigned char>(byte)));
  }
  const std::uint64_t bit_length = static_cast<std::uint64_t>(source.size()) * 8U;
  message.push_back(0x80U);
  while (message.size() % 64U != 56U) {
    message.push_back(0U);
  }
  for (int shift = 56; shift >= 0; shift -= 8) {
    message.push_back(static_cast<std::uint8_t>(bit_length >> shift));
  }

  static constexpr std::array<std::uint32_t, 64> kRoundConstants = {
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
      0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U,
  };
  std::array<std::uint32_t, 8> state = {
      0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
      0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U,
  };

  for (std::size_t block = 0; block < message.size(); block += 64U) {
    std::array<std::uint32_t, 64> words{};
    for (std::size_t index = 0; index < 16U; ++index) {
      const std::size_t offset = block + index * 4U;
      words[index] = (static_cast<std::uint32_t>(message[offset]) << 24U) |
                     (static_cast<std::uint32_t>(message[offset + 1U]) << 16U) |
                     (static_cast<std::uint32_t>(message[offset + 2U]) << 8U) |
                     static_cast<std::uint32_t>(message[offset + 3U]);
    }
    for (std::size_t index = 16U; index < words.size(); ++index) {
      const std::uint32_t sigma0 = rotate_right(words[index - 15U], 7U) ^
                                   rotate_right(words[index - 15U], 18U) ^
                                   (words[index - 15U] >> 3U);
      const std::uint32_t sigma1 = rotate_right(words[index - 2U], 17U) ^
                                   rotate_right(words[index - 2U], 19U) ^
                                   (words[index - 2U] >> 10U);
      words[index] = words[index - 16U] + sigma0 + words[index - 7U] + sigma1;
    }

    std::uint32_t a = state[0];
    std::uint32_t b = state[1];
    std::uint32_t c = state[2];
    std::uint32_t d = state[3];
    std::uint32_t e = state[4];
    std::uint32_t f = state[5];
    std::uint32_t g = state[6];
    std::uint32_t h = state[7];
    for (std::size_t index = 0; index < words.size(); ++index) {
      const std::uint32_t sum1 = rotate_right(e, 6U) ^ rotate_right(e, 11U) ^
                                 rotate_right(e, 25U);
      const std::uint32_t choose = (e & f) ^ ((~e) & g);
      const std::uint32_t temporary1 =
          h + sum1 + choose + kRoundConstants[index] + words[index];
      const std::uint32_t sum0 = rotate_right(a, 2U) ^ rotate_right(a, 13U) ^
                                 rotate_right(a, 22U);
      const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
      const std::uint32_t temporary2 = sum0 + majority;
      h = g;
      g = f;
      f = e;
      e = d + temporary1;
      d = c;
      c = b;
      b = a;
      a = temporary1 + temporary2;
    }
    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
  }

  static constexpr char kHexDigits[] = "0123456789abcdef";
  std::string digest;
  digest.reserve(64U);
  for (const std::uint32_t word : state) {
    for (int shift = 28; shift >= 0; shift -= 4) {
      digest.push_back(kHexDigits[(word >> shift) & 0x0fU]);
    }
  }
  return digest;
}

struct JsonValue {
  enum class Kind { kNull, kBoolean, kNumber, kString, kArray, kObject };

  Kind kind = Kind::kNull;
  bool boolean = false;
  double number = 0.0;
  std::string string;
  std::vector<JsonValue> array;
  std::map<std::string, JsonValue> object;
};

class JsonParser {
 public:
  explicit JsonParser(std::string_view source) : source_(source) {}

  JsonValue parse_document() {
    skip_whitespace();
    JsonValue value = parse_value();
    skip_whitespace();
    if (position_ != source_.size()) {
      fail("unexpected trailing content");
    }
    return value;
  }

 private:
  [[noreturn]] void fail(const std::string& message) const {
    throw std::runtime_error("canonical map2 JSON parse error at byte " +
                             std::to_string(position_) + ": " + message);
  }

  void skip_whitespace() {
    while (position_ < source_.size()) {
      const char ch = source_[position_];
      if (ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n') {
        break;
      }
      ++position_;
    }
  }

  char take() {
    if (position_ >= source_.size()) {
      fail("unexpected end of input");
    }
    return source_[position_++];
  }

  bool consume(char expected) {
    if (position_ < source_.size() && source_[position_] == expected) {
      ++position_;
      return true;
    }
    return false;
  }

  void expect(char expected) {
    if (!consume(expected)) {
      fail(std::string("expected '") + expected + "'");
    }
  }

  JsonValue parse_value() {
    skip_whitespace();
    if (position_ >= source_.size()) {
      fail("expected a JSON value");
    }
    switch (source_[position_]) {
      case '{':
        return parse_object();
      case '[':
        return parse_array();
      case '"': {
        JsonValue value;
        value.kind = JsonValue::Kind::kString;
        value.string = parse_string();
        return value;
      }
      case 't':
        return parse_literal("true", JsonValue::Kind::kBoolean, true);
      case 'f':
        return parse_literal("false", JsonValue::Kind::kBoolean, false);
      case 'n':
        return parse_literal("null", JsonValue::Kind::kNull, false);
      default:
        if (source_[position_] == '-' ||
            (source_[position_] >= '0' && source_[position_] <= '9')) {
          return parse_number();
        }
        fail("invalid JSON value");
    }
  }

  JsonValue parse_literal(std::string_view literal,
                          JsonValue::Kind kind,
                          bool boolean) {
    if (source_.substr(position_, literal.size()) != literal) {
      fail("invalid literal");
    }
    position_ += literal.size();
    JsonValue value;
    value.kind = kind;
    value.boolean = boolean;
    return value;
  }

  JsonValue parse_object() {
    expect('{');
    JsonValue value;
    value.kind = JsonValue::Kind::kObject;
    skip_whitespace();
    if (consume('}')) {
      return value;
    }
    while (true) {
      skip_whitespace();
      if (position_ >= source_.size() || source_[position_] != '"') {
        fail("object key must be a string");
      }
      std::string key = parse_string();
      skip_whitespace();
      expect(':');
      JsonValue child = parse_value();
      if (!value.object.emplace(std::move(key), std::move(child)).second) {
        fail("duplicate object key");
      }
      skip_whitespace();
      if (consume('}')) {
        break;
      }
      expect(',');
    }
    return value;
  }

  JsonValue parse_array() {
    expect('[');
    JsonValue value;
    value.kind = JsonValue::Kind::kArray;
    skip_whitespace();
    if (consume(']')) {
      return value;
    }
    while (true) {
      value.array.push_back(parse_value());
      skip_whitespace();
      if (consume(']')) {
        break;
      }
      expect(',');
    }
    return value;
  }

  static int hex_value(char ch) {
    if (ch >= '0' && ch <= '9') {
      return ch - '0';
    }
    if (ch >= 'a' && ch <= 'f') {
      return ch - 'a' + 10;
    }
    if (ch >= 'A' && ch <= 'F') {
      return ch - 'A' + 10;
    }
    return -1;
  }

  std::uint32_t parse_hex_quad() {
    std::uint32_t value = 0;
    for (int index = 0; index < 4; ++index) {
      const int digit = hex_value(take());
      if (digit < 0) {
        fail("invalid Unicode escape");
      }
      value = value * 16U + static_cast<std::uint32_t>(digit);
    }
    return value;
  }

  static void append_utf8(std::string& output, std::uint32_t codepoint) {
    if (codepoint <= 0x7FU) {
      output.push_back(static_cast<char>(codepoint));
    } else if (codepoint <= 0x7FFU) {
      output.push_back(static_cast<char>(0xC0U | (codepoint >> 6U)));
      output.push_back(static_cast<char>(0x80U | (codepoint & 0x3FU)));
    } else if (codepoint <= 0xFFFFU) {
      output.push_back(static_cast<char>(0xE0U | (codepoint >> 12U)));
      output.push_back(static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3FU)));
      output.push_back(static_cast<char>(0x80U | (codepoint & 0x3FU)));
    } else {
      output.push_back(static_cast<char>(0xF0U | (codepoint >> 18U)));
      output.push_back(static_cast<char>(0x80U | ((codepoint >> 12U) & 0x3FU)));
      output.push_back(static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3FU)));
      output.push_back(static_cast<char>(0x80U | (codepoint & 0x3FU)));
    }
  }

  std::string parse_string() {
    expect('"');
    std::string output;
    while (true) {
      const char ch = take();
      if (ch == '"') {
        return output;
      }
      if (static_cast<unsigned char>(ch) < 0x20U) {
        fail("unescaped control character in string");
      }
      if (ch != '\\') {
        output.push_back(ch);
        continue;
      }
      const char escape = take();
      switch (escape) {
        case '"':
        case '\\':
        case '/':
          output.push_back(escape);
          break;
        case 'b':
          output.push_back('\b');
          break;
        case 'f':
          output.push_back('\f');
          break;
        case 'n':
          output.push_back('\n');
          break;
        case 'r':
          output.push_back('\r');
          break;
        case 't':
          output.push_back('\t');
          break;
        case 'u': {
          std::uint32_t codepoint = parse_hex_quad();
          if (codepoint >= 0xD800U && codepoint <= 0xDBFFU) {
            if (take() != '\\' || take() != 'u') {
              fail("high surrogate must be followed by a low surrogate");
            }
            const std::uint32_t low = parse_hex_quad();
            if (low < 0xDC00U || low > 0xDFFFU) {
              fail("invalid low surrogate");
            }
            codepoint = 0x10000U + ((codepoint - 0xD800U) << 10U) +
                        (low - 0xDC00U);
          } else if (codepoint >= 0xDC00U && codepoint <= 0xDFFFU) {
            fail("unexpected low surrogate");
          }
          append_utf8(output, codepoint);
          break;
        }
        default:
          fail("invalid string escape");
      }
    }
  }

  JsonValue parse_number() {
    const std::size_t begin = position_;
    consume('-');
    if (consume('0')) {
      if (position_ < source_.size() && source_[position_] >= '0' &&
          source_[position_] <= '9') {
        fail("leading zero in number");
      }
    } else {
      if (position_ >= source_.size() || source_[position_] < '1' ||
          source_[position_] > '9') {
        fail("invalid number integer part");
      }
      while (position_ < source_.size() && source_[position_] >= '0' &&
             source_[position_] <= '9') {
        ++position_;
      }
    }
    if (consume('.')) {
      if (position_ >= source_.size() || source_[position_] < '0' ||
          source_[position_] > '9') {
        fail("invalid number fraction");
      }
      while (position_ < source_.size() && source_[position_] >= '0' &&
             source_[position_] <= '9') {
        ++position_;
      }
    }
    if (position_ < source_.size() &&
        (source_[position_] == 'e' || source_[position_] == 'E')) {
      ++position_;
      if (position_ < source_.size() &&
          (source_[position_] == '+' || source_[position_] == '-')) {
        ++position_;
      }
      if (position_ >= source_.size() || source_[position_] < '0' ||
          source_[position_] > '9') {
        fail("invalid number exponent");
      }
      while (position_ < source_.size() && source_[position_] >= '0' &&
             source_[position_] <= '9') {
        ++position_;
      }
    }

    const std::string token(source_.substr(begin, position_ - begin));
    std::size_t consumed = 0;
    double parsed = 0.0;
    try {
      parsed = std::stod(token, &consumed);
    } catch (const std::exception&) {
      fail("number is outside the supported range");
    }
    if (consumed != token.size() || !std::isfinite(parsed)) {
      fail("invalid finite number");
    }
    JsonValue value;
    value.kind = JsonValue::Kind::kNumber;
    value.number = parsed;
    return value;
  }

  std::string_view source_;
  std::size_t position_ = 0;
};

inline const JsonValue& require_field(const JsonValue& value,
                                      const std::string& key,
                                      const std::string& context) {
  if (value.kind != JsonValue::Kind::kObject) {
    throw std::runtime_error(context + " must be a JSON object");
  }
  const auto found = value.object.find(key);
  if (found == value.object.end()) {
    throw std::runtime_error(context + " is missing required field '" + key + "'");
  }
  return found->second;
}

inline const std::vector<JsonValue>& require_array(const JsonValue& value,
                                                   const std::string& context) {
  if (value.kind != JsonValue::Kind::kArray) {
    throw std::runtime_error(context + " must be a JSON array");
  }
  return value.array;
}

inline std::string require_string(const JsonValue& value, const std::string& context) {
  if (value.kind != JsonValue::Kind::kString) {
    throw std::runtime_error(context + " must be a JSON string");
  }
  return value.string;
}

inline double require_number(const JsonValue& value, const std::string& context) {
  if (value.kind != JsonValue::Kind::kNumber || !std::isfinite(value.number)) {
    throw std::runtime_error(context + " must be a finite JSON number");
  }
  return value.number;
}

inline int require_integer(const JsonValue& value, const std::string& context) {
  const double number = require_number(value, context);
  if (std::floor(number) != number ||
      number < static_cast<double>(std::numeric_limits<int>::min()) ||
      number > static_cast<double>(std::numeric_limits<int>::max())) {
    throw std::runtime_error(context + " must be an integer in range");
  }
  return static_cast<int>(number);
}

inline std::vector<int> require_integer_array(const JsonValue& value,
                                              const std::string& context) {
  const auto& array = require_array(value, context);
  std::vector<int> result;
  result.reserve(array.size());
  for (std::size_t index = 0; index < array.size(); ++index) {
    result.push_back(require_integer(array[index],
                                     context + "[" + std::to_string(index) + "]"));
  }
  return result;
}

inline void require_node_index(int node, int node_count, const std::string& context) {
  if (node < 0 || node >= node_count) {
    throw std::runtime_error(context + " is outside [0, node_count)");
  }
}

}  // namespace canonical_map2_detail

struct CanonicalMap2ReadResult {
  Graph graph;
  std::string schema;
  std::string normalized_sha256;
  int declared_node_count = 0;
  std::size_t edge_count = 0;
  std::vector<int> start_nodes;
  std::vector<int> end_nodes;
};

inline CanonicalMap2ReadResult read_canonical_map2_json(
    const std::filesystem::path& path) {
  if (path.filename() != "map2.json") {
    throw std::runtime_error("canonical map path must end in map2.json: " + path.string());
  }
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    throw std::runtime_error("failed to open canonical map2 JSON: " + path.string());
  }
  const std::string source((std::istreambuf_iterator<char>(input)),
                           std::istreambuf_iterator<char>());
  if (input.bad()) {
    throw std::runtime_error("failed while reading canonical map2 JSON: " + path.string());
  }

  using namespace canonical_map2_detail;
  const std::string normalized_source = normalize_newlines(source);
  const std::string normalized_sha256 = sha256_hex(normalized_source);
  if (normalized_sha256 != kCanonicalMap2NormalizedSha256) {
    throw std::runtime_error(
        "canonical map2 normalized SHA-256 mismatch: expected " +
        std::string(kCanonicalMap2NormalizedSha256) + ", got " + normalized_sha256);
  }

  const JsonValue root = JsonParser(normalized_source).parse_document();
  CanonicalMap2ReadResult result;
  result.normalized_sha256 = normalized_sha256;
  result.schema = require_string(require_field(root, "schema", "root"), "root.schema");
  if (result.schema != "czr005.legacy_map.v1") {
    throw std::runtime_error("unsupported canonical map2 schema: " + result.schema);
  }

  const JsonValue& header = require_field(root, "header", "root");
  result.declared_node_count = require_integer(
      require_field(header, "node_count", "root.header"), "root.header.node_count");
  if (result.declared_node_count <= 0) {
    throw std::runtime_error("root.header.node_count must be positive");
  }

  const auto& node_rows = require_array(require_field(root, "nodes", "root"), "root.nodes");
  if (node_rows.size() != static_cast<std::size_t>(result.declared_node_count)) {
    throw std::runtime_error("root.nodes length does not match root.header.node_count");
  }

  std::vector<Node> nodes(static_cast<std::size_t>(result.declared_node_count));
  std::vector<bool> seen_nodes(static_cast<std::size_t>(result.declared_node_count), false);
  std::vector<int> node_types(static_cast<std::size_t>(result.declared_node_count), 0);
  std::set<std::pair<int, int>> outgoing_pairs;
  for (std::size_t row_index = 0; row_index < node_rows.size(); ++row_index) {
    const JsonValue& row = node_rows[row_index];
    const std::string context = "root.nodes[" + std::to_string(row_index) + "]";
    Node node;
    node.location = require_integer(require_field(row, "location", context),
                                    context + ".location");
    require_node_index(node.location, result.declared_node_count, context + ".location");
    if (seen_nodes[static_cast<std::size_t>(node.location)]) {
      throw std::runtime_error("duplicate node location " + std::to_string(node.location));
    }
    node.node_type = require_integer(require_field(row, "node_type", context),
                                     context + ".node_type");
    node.service_time = require_number(require_field(row, "service_time", context),
                                       context + ".service_time");
    if (node.service_time < 0.0) {
      throw std::runtime_error(context + ".service_time must be non-negative");
    }
    node.x = require_integer(require_field(row, "x", context), context + ".x");
    node.y = require_integer(require_field(row, "y", context), context + ".y");
    node.outgoing = require_integer_array(require_field(row, "outgoing", context),
                                          context + ".outgoing");
    for (const int next : node.outgoing) {
      require_node_index(next, result.declared_node_count, context + ".outgoing entry");
      if (!outgoing_pairs.emplace(node.location, next).second) {
        throw std::runtime_error("duplicate outgoing edge " + std::to_string(node.location) +
                                 "->" + std::to_string(next));
      }
    }
    seen_nodes[static_cast<std::size_t>(node.location)] = true;
    node_types[static_cast<std::size_t>(node.location)] = node.node_type;
    nodes[static_cast<std::size_t>(node.location)] = std::move(node);
  }

  result.start_nodes = require_integer_array(require_field(root, "start_nodes", "root"),
                                             "root.start_nodes");
  result.end_nodes = require_integer_array(require_field(root, "end_nodes", "root"),
                                           "root.end_nodes");
  std::set<int> unique_starts;
  for (const int node : result.start_nodes) {
    require_node_index(node, result.declared_node_count, "root.start_nodes entry");
    if (!unique_starts.insert(node).second ||
        node_types[static_cast<std::size_t>(node)] != 1) {
      throw std::runtime_error("root.start_nodes must uniquely reference type-1 nodes");
    }
  }
  std::set<int> unique_ends;
  for (const int node : result.end_nodes) {
    require_node_index(node, result.declared_node_count, "root.end_nodes entry");
    if (!unique_ends.insert(node).second || node_types[static_cast<std::size_t>(node)] != 2 ||
        !nodes[static_cast<std::size_t>(node)].outgoing.empty()) {
      throw std::runtime_error(
          "root.end_nodes must uniquely reference terminal type-2 nodes");
    }
  }

  const auto& edge_rows = require_array(require_field(root, "edges", "root"), "root.edges");
  std::vector<Edge> edges;
  edges.reserve(edge_rows.size());
  std::set<std::pair<int, int>> edge_pairs;
  for (std::size_t row_index = 0; row_index < edge_rows.size(); ++row_index) {
    const JsonValue& row = edge_rows[row_index];
    const std::string context = "root.edges[" + std::to_string(row_index) + "]";
    Edge edge;
    edge.start = require_integer(require_field(row, "start", context), context + ".start");
    edge.end = require_integer(require_field(row, "end", context), context + ".end");
    require_node_index(edge.start, result.declared_node_count, context + ".start");
    require_node_index(edge.end, result.declared_node_count, context + ".end");
    edge.length = require_number(require_field(row, "length", context), context + ".length");
    edge.speed = require_number(require_field(row, "speed", context), context + ".speed");
    if (edge.length <= 0.0 || edge.speed <= 0.0) {
      throw std::runtime_error(context + " length and speed must be positive");
    }
    if (!edge_pairs.emplace(edge.start, edge.end).second) {
      throw std::runtime_error("duplicate edge row " + std::to_string(edge.start) + "->" +
                               std::to_string(edge.end));
    }
    edges.push_back(edge);
  }
  if (edge_pairs != outgoing_pairs) {
    throw std::runtime_error("node outgoing lists and root.edges do not describe the same graph");
  }
  result.edge_count = edges.size();

  const auto& heuristic_rows = require_array(
      require_field(root, "heuristic_time", "root"), "root.heuristic_time");
  if (heuristic_rows.size() != static_cast<std::size_t>(result.declared_node_count)) {
    throw std::runtime_error("root.heuristic_time row count does not match node_count");
  }
  std::vector<std::vector<double>> heuristic;
  heuristic.reserve(heuristic_rows.size());
  for (std::size_t row_index = 0; row_index < heuristic_rows.size(); ++row_index) {
    const std::string context =
        "root.heuristic_time[" + std::to_string(row_index) + "]";
    const auto& values = require_array(heuristic_rows[row_index], context);
    if (values.size() != static_cast<std::size_t>(result.declared_node_count)) {
      throw std::runtime_error(context + " width does not match node_count");
    }
    std::vector<double> parsed_row;
    parsed_row.reserve(values.size());
    for (std::size_t column = 0; column < values.size(); ++column) {
      const double value = require_number(
          values[column], context + "[" + std::to_string(column) + "]");
      if (value < 0.0) {
        throw std::runtime_error(context + " contains a negative potential");
      }
      parsed_row.push_back(value);
    }
    heuristic.push_back(std::move(parsed_row));
  }

  for (Node& node : nodes) {
    result.graph.add_node(std::move(node));
  }
  result.graph.set_heuristic(std::move(heuristic));
  for (const Edge& edge : edges) {
    result.graph.add_edge(edge);
  }
  if (result.graph.node_count() != static_cast<std::size_t>(result.declared_node_count) ||
      result.graph.edge_count() != result.edge_count) {
    throw std::runtime_error("canonical map2 graph construction lost nodes or edges");
  }
  return result;
}

}  // namespace czr005::ics
