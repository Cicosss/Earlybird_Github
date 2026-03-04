#!/usr/bin/env ruby
# Test script for FotMob Ruby wrapper
# This script tests if the Ruby wrapper can bypass FotMob's 403 blocking

require 'json'
require 'net/http'
require 'uri'

# Test 1: Try using the fotmob gem
puts "=" * 60
puts "TEST 1: Using fotmob gem"
puts "=" * 60

begin
  require 'fotmob'
  
  client = Fotmob.new
  
  # Try to get team information (Palermo ID: 8540)
  puts "Attempting to get team info for Palermo (ID: 8540)..."
  
  team = client.get_team("8540")
  
  if team
    puts "✅ SUCCESS: Got team data"
    puts "Team name: #{team[:details][:name]}" if team[:details]
    puts "Full response: #{JSON.pretty_generate(team)}"
  else
    puts "❌ FAILED: No data returned"
  end
  
rescue LoadError => e
  puts "❌ FAILED: Could not load fotmob gem"
  puts "Error: #{e.message}"
  puts "Make sure to install with: sudo gem install fotmob"
  
rescue => e
  puts "❌ FAILED: #{e.class}"
  puts "Error: #{e.message}"
  puts "Backtrace:"
  puts e.backtrace.first(5).join("\n")
end

# Test 2: Direct HTTP request with Ruby (to compare with Python requests)
puts "\n" + "=" * 60
puts "TEST 2: Direct HTTP request with Ruby (Net::HTTP)"
puts "=" * 60

begin
  uri = URI.parse("https://www.fotmob.com/api/search/suggest?term=Palermo")
  
  http = Net::HTTP.new(uri.host, uri.port)
  http.use_ssl = true
  http.read_timeout = 10
  
  request = Net::HTTP::Get.new(uri.request_uri)
  request["Accept"] = "application/json, text/plain, */*"
  request["Accept-Language"] = "en-US,en;q=0.9"
  request["Referer"] = "https://www.fotmob.com/"
  request["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  
  puts "Making request to: #{uri.to_s}"
  
  response = http.request(request)
  
  puts "\nResponse status: #{response.code} #{response.message}"
  
  if response.code.to_i == 200
    puts "✅ SUCCESS: Got 200 OK"
    data = JSON.parse(response.body)
    puts "Response keys: #{data.keys.join(', ')}"
  elsif response.code.to_i == 403
    puts "❌ FAILED: Got 403 Forbidden"
    puts "Ruby Net::HTTP also blocked by FotMob anti-bot system"
  else
    puts "⚠️  Got status code: #{response.code}"
    puts "Response body (first 500 chars):"
    puts response.body[0..500]
  end
  
rescue => e
  puts "❌ FAILED: #{e.class}"
  puts "Error: #{e.message}"
  puts "Backtrace:"
  puts e.backtrace.first(5).join("\n")
end

puts "\n" + "=" * 60
puts "CONCLUSION"
puts "=" * 60
puts "If both tests fail with 403, this confirms that:"
puts "1. The fotmob Ruby gem does NOT bypass FotMob's anti-bot system"
puts "2. Ruby Net::HTTP has the same TLS fingerprint issues as Python requests"
puts "3. The solution requires browser-based scraping (Playwright with stealth)"
