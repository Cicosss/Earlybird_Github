#!/usr/bin/env python3
"""Test to verify Enum behavior with Pydantic model_dump()"""

from enum import Enum

from pydantic import BaseModel, Field


class CardsSignal(str, Enum):
    """Cards signal levels."""

    AGGRESSIVE = "Aggressive"
    MEDIUM = "Medium"
    DISCIPLINED = "Disciplined"
    UNKNOWN = "Unknown"


class BettingStatsResponse(BaseModel):
    """Test model similar to the real one."""

    cards_signal: CardsSignal = Field(default=CardsSignal.UNKNOWN, description="Cards signal level")


# Test 1: Create instance with enum
response1 = BettingStatsResponse(cards_signal=CardsSignal.AGGRESSIVE)
print("Test 1: Instance with enum")
print(f"  Type: {type(response1.cards_signal)}")
print(f"  Value: {response1.cards_signal}")
print(f"  Is str: {isinstance(response1.cards_signal, str)}")
print(f"  Is Enum: {isinstance(response1.cards_signal, Enum)}")
print(f"  Comparison with string: {response1.cards_signal == 'Aggressive'}")
print()

# Test 2: Create instance with string
response2 = BettingStatsResponse(cards_signal="Aggressive")
print("Test 2: Instance with string")
print(f"  Type: {type(response2.cards_signal)}")
print(f"  Value: {response2.cards_signal}")
print(f"  Is str: {isinstance(response2.cards_signal, str)}")
print(f"  Is Enum: {isinstance(response2.cards_signal, Enum)}")
print(f"  Comparison with string: {response2.cards_signal == 'Aggressive'}")
print()

# Test 3: model_dump() with default mode
dump1 = response1.model_dump()
print("Test 3: model_dump() from enum instance")
print(f"  Type: {type(dump1['cards_signal'])}")
print(f"  Value: {dump1['cards_signal']}")
print(f"  Is str: {isinstance(dump1['cards_signal'], str)}")
print(f"  Is Enum: {isinstance(dump1['cards_signal'], Enum)}")
print(f"  Comparison with string: {dump1['cards_signal'] == 'Aggressive'}")
print()

# Test 4: model_dump() from string instance
dump2 = response2.model_dump()
print("Test 4: model_dump() from string instance")
print(f"  Type: {type(dump2['cards_signal'])}")
print(f"  Value: {dump2['cards_signal']}")
print(f"  Is str: {isinstance(dump2['cards_signal'], str)}")
print(f"  Is Enum: {isinstance(dump2['cards_signal'], Enum)}")
print(f"  Comparison with string: {dump2['cards_signal'] == 'Aggressive'}")
print()

# Test 5: Simulate the actual usage pattern
print("Test 5: Simulating actual usage pattern")
cards_data = dump1  # This is what model_dump() returns
cards_signal = cards_data.get("cards_signal", "Unknown")
print(f"  Extracted type: {type(cards_signal)}")
print(f"  Extracted value: {cards_signal}")
print(f"  Comparison with string: {cards_signal == 'Aggressive'}")
print()

# Test 6: Assign to a dataclass field
from dataclasses import dataclass


@dataclass
class VerifiedData:
    cards_signal: str = "Unknown"


verified = VerifiedData()
verified.cards_signal = cards_data.get("cards_signal", "Unknown")
print("Test 6: Assign to dataclass field")
print(f"  Field type: {type(verified.cards_signal)}")
print(f"  Field value: {verified.cards_signal}")
print(f"  Comparison with string: {verified.cards_signal == 'Aggressive'}")
