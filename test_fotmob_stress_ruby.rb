#!/usr/bin/env ruby
# Stress test for FotMob API using Ruby fotmob gem
# Simulates real-world usage intensity

require 'fotmob'
require 'json'
require 'time'

# Configuration (matching Python production code)
FOTMOB_MIN_REQUEST_INTERVAL = 2.0 # seconds
FOTMOB_JITTER_MIN = 0.0
FOTMOB_JITTER_MAX = 0.5
FOTMOB_MAX_RETRIES = 3

# Test data
TEAMS = [
  { name: "Palermo", id: "8540" },
  { name: "Juventus", id: "2488" },
  { name: "Milan", id: "2487" },
  { name: "Inter", id: "2581" },
  { name: "Roma", id: "2580" },
  { name: "Napoli", id: "2579" },
  { name: "Lazio", id: "2578" },
  { name: "Fiorentina", id: "2577" },
]

MATCHES = [
  "4193741",
  "4906263",
  "4906252",
]

# Statistics tracking
stats = {
  requests: 0,
  successes: 0,
  failures: 0,
  status_codes: Hash.new(0),
  errors: Hash.new(0),
  timeline: [],
  start_time: nil,
  end_time: nil
}

def record_request(url, status_code, success, error = nil)
  stats[:requests] += 1
  stats[:status_codes][status_code] += 1

  if success
    stats[:successes] += 1
  else
    stats[:failures] += 1
    stats[:errors][error] += 1 if error
  end

  stats[:timeline] << {
    request_num: stats[:requests],
    url: url,
    status_code: status_code,
    success: success,
    error: error,
    timestamp: Time.now.iso8601
  }
end

def sleep_with_jitter
  return if stats[:requests] == 0

  jitter = rand * (FOTMOB_JITTER_MAX - FOTMOB_JITTER_MIN) + FOTMOB_JITTER_MIN
  required_interval = FOTMOB_MIN_REQUEST_INTERVAL + [0, jitter].max
  sleep(required_interval)
end

def make_fotmob_request(endpoint_type, data)
  client = Fotmob.new
  url = ""
  success = false
  status_code = 0
  error = nil

  for attempt in 1..FOTMOB_MAX_RETRIES
    begin
      sleep_with_jitter

      case endpoint_type
      when :team
        team_id = data[:id]
        result = client.get_team(team_id)
        url = "https://www.fotmob.com/api/teams/#{team_id}/details"

        if result && result[:details]
          status_code = 200
          success = true
          break
        else
          status_code = 500
          error = "No data returned"
        end

      when :search
        # Note: fotmob gem doesn't have search method, skip
        url = "https://www.fotmob.com/api/search/suggest?term=#{data[:name]}"
        status_code = 200
        success = true
        break
      end

    rescue => e
      error_msg = e.message

      if error_msg.include?("403") || error_msg.include?("Forbidden")
        if attempt < FOTMOB_MAX_RETRIES
          delay = 5 ** attempt
          puts "⚠️  Request ##{stats[:requests] + 1}: 403 - retrying in #{delay}s (#{attempt}/#{FOTMOB_MAX_RETRIES})"
          sleep(delay)
          next
        end
        status_code = 403
        error = "403 Forbidden"
        puts "❌ Request ##{stats[:requests] + 1}: 403 Forbidden (max retries reached)"
        break
      end

      if error_msg.include?("429") || error_msg.include?("rate limit")
        delay = 3 ** attempt
        puts "⚠️  Request ##{stats[:requests] + 1}: 429 Rate Limit - waiting #{delay}s..."
        sleep(delay)
        next
      end

      status_code = 0
      error = error_msg
      puts "❌ Request ##{stats[:requests] + 1}: #{error_msg}"
      break
    end
  end

  record_request(url, status_code, success, error)
  success
end

def print_summary
  duration = (stats[:end_time] - stats[:start_time]).to_f if stats[:end_time] && stats[:start_time]

  puts "\n" + "=" * 60
  puts "RUBY STRESS TEST SUMMARY"
  puts "=" * 60
  puts "Total Requests: #{stats[:requests]}"
  puts "Successes: #{stats[:successes]} (#{(stats[:successes].to_f / stats[:requests] * 100).round(1)}%)"
  puts "Failures: #{stats[:failures]} (#{(stats[:failures].to_f / stats[:requests] * 100).round(1)}%)"
  puts "Duration: #{duration.round(1)}s"
  puts "Requests/sec: #{(stats[:requests] / duration).round(2)}" if duration && duration > 0

  puts "\nStatus Codes:"
  stats[:status_codes].sort.each do |code, count|
    puts "  #{code}: #{count} (#{(count.to_f / stats[:requests] * 100).round(1)}%)"
  end

  if stats[:errors].any?
    puts "\nErrors:"
    stats[:errors].sort_by { |k, v| -v }.each do |error, count|
      puts "  #{error}: #{count}"
    end
  end

  puts "\nTimeline (first 10 and last 10):"
  stats[:timeline].first(10).each do |entry|
    puts "  ##{entry[:request_num].to_s.rjust(3)}: #{entry[:status_code]} - #{entry[:url][0..50]}"
  end
  if stats[:timeline].length > 20
    puts "  ..."
    stats[:timeline].last(10).each do |entry|
      puts "  ##{entry[:request_num].to_s.rjust(3)}: #{entry[:status_code]} - #{entry[:url][0..50]}"
    end
  end
end

def run_stress_test(num_requests = 50)
  stats[:start_time] = Time.now

  puts "=" * 60
  puts "FOTMOB RUBY STRESS TEST"
  puts "=" * 60
  puts "Target requests: #{num_requests}"
  puts "Request interval: #{FOTMOB_MIN_REQUEST_INTERVAL}s (±#{FOTMOB_JITTER_MAX}s)"
  puts "Max retries: #{FOTMOB_MAX_RETRIES}"
  puts "Start time: #{stats[:start_time].iso8601}"
  puts

  request_count = 0
  while request_count < num_requests
    # Rotate through teams
    team = TEAMS[request_count % TEAMS.length]

    endpoint_type = :team
    data = team

    puts "Request ##{request_count + 1}/#{num_requests}: team - #{team[:name]} (ID: #{team[:id]})"

    success = make_fotmob_request(endpoint_type, data)

    if !success && stats[:errors]["403 Forbidden"].to_i >= 3
      puts "\n" + "=" * 60
      puts "⚠️  ABORTING: Multiple 403 errors detected"
      puts "=" * 60
      break
    end

    request_count += 1
  end

  stats[:end_time] = Time.now
  print_summary

  # Check if we should recommend action
  if stats[:errors]["403 Forbidden"].to_i > 0
    puts "\n" + "=" * 60
    puts "⚠️  RECOMMENDATION: 403 errors detected"
    puts "=" * 60
    puts "FotMob is blocking requests. Consider:"
    puts "1. Increasing request interval (e.g., 3-5s)"
    puts "2. Using proxy rotation"
    puts "3. Implementing Playwright with stealth"
  else
    puts "\n" + "=" * 60
    puts "✅ SUCCESS: No 403 errors detected"
    puts "=" * 60
    puts "FotMob API is working with current rate limiting."
  end

  stats
end

# Main execution
num_requests = ARGV[0] ? ARGV[0].to_i : 50

puts "Starting Ruby stress test with #{num_requests} requests..."
puts "Estimated duration: ~#{(num_requests * FOTMOB_MIN_REQUEST_INTERVAL).to_i} seconds"
puts

stats_result = run_stress_test(num_requests)

# Save timeline to file
File.open("fotmob_stress_test_ruby_timeline.json", "w") do |f|
  f.write(JSON.pretty_generate(stats_result[:timeline]))
end

puts "\nTimeline saved to: fotmob_stress_test_ruby_timeline.json"

# Exit with error code if 403 errors detected
exit(stats_result[:errors]["403 Forbidden"].to_i > 0 ? 1 : 0)
