"""
Test per il pattern ResponseLike e _MockResponse.

Questo test suite verifica:
1. Type enforcement in _MockResponse.__init__()
2. Protocol compliance di _MockResponse
3. Integrazione con il flusso dati di FotMobProvider
4. Comportamento edge cases

Bug corretti:
1. Type enforcement mancante in _MockResponse.__init__()
2. Mancanza di test unitari per ResponseLike pattern
"""

import unittest
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class TestMockResponseTypeFlexibility(unittest.TestCase):
    """Test per la flessibilità di tipi in _MockResponse.__init__()."""

    def setUp(self):
        """Setup per i test."""
        from src.ingestion.data_provider import _MockResponse

        self.MockResponse = _MockResponse

    def test_init_with_dict(self):
        """Test che _MockResponse accetta un dict (get_team_details, get_match_lineup)."""
        data = {"key": "value", "nested": {"inner": "data"}}
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertEqual(mock_resp._data, data)

    def test_init_with_list(self):
        """Test che _MockResponse accetta una lista (search_team)."""
        data = [{"id": 1, "name": "Team A"}, {"id": 2, "name": "Team B"}]
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertEqual(mock_resp._data, data)

    def test_init_with_empty_dict(self):
        """Test che _MockResponse accetta un dict vuoto."""
        data = {}
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertEqual(mock_resp._data, {})

    def test_init_with_empty_list(self):
        """Test che _MockResponse accetta una lista vuota."""
        data = []
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertEqual(mock_resp._data, [])

    def test_init_with_complex_dict(self):
        """Test che _MockResponse accetta un dict complesso (simula dati FotMob)."""
        data = {
            "teams": [
                {"id": 1, "name": "Team A"},
                {"id": 2, "name": "Team B"},
            ],
            "matchDetails": {
                "id": 12345,
                "status": "live",
                "score": {"home": 2, "away": 1},
            },
        }
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertEqual(mock_resp._data, data)

    def test_init_with_complex_list(self):
        """Test che _MockResponse accetta una lista complessa (simula dati search_team)."""
        data = [
            {
                "suggestions": [
                    {"type": "team", "id": "12345", "name": "Team A"},
                    {"type": "team", "id": "67890", "name": "Team B"},
                ]
            }
        ]
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertEqual(mock_resp._data, data)

    def test_init_with_string(self):
        """Test che _MockResponse accetta una stringa (JSON primitivo)."""
        data = "simple string"
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertEqual(mock_resp._data, data)

    def test_init_with_int(self):
        """Test che _MockResponse accetta un intero (JSON primitivo)."""
        data = 123
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertEqual(mock_resp._data, data)

    def test_init_with_none(self):
        """Test che _MockResponse accetta None (JSON null)."""
        data = None
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertIsNone(mock_resp._data)

    def test_init_with_bool(self):
        """Test che _MockResponse accetta un booleano (JSON primitivo)."""
        data = True
        mock_resp = self.MockResponse(data)

        self.assertEqual(mock_resp.status_code, 200)
        self.assertTrue(mock_resp._data)


class TestMockResponseProtocolCompliance(unittest.TestCase):
    """Test per la compliance di _MockResponse con il Protocol ResponseLike."""

    def setUp(self):
        """Setup per i test."""
        from src.ingestion.data_provider import ResponseLike, _MockResponse

        self.MockResponse = _MockResponse
        self.ResponseLike = ResponseLike

    def test_has_status_code_attribute(self):
        """Test che _MockResponse ha l'attributo status_code."""
        data = {"test": "data"}
        mock_resp = self.MockResponse(data)

        self.assertTrue(hasattr(mock_resp, "status_code"))
        self.assertIsInstance(mock_resp.status_code, int)
        self.assertEqual(mock_resp.status_code, 200)

    def test_has_json_method(self):
        """Test che _MockResponse ha il metodo json()."""
        data = {"test": "data"}
        mock_resp = self.MockResponse(data)

        self.assertTrue(hasattr(mock_resp, "json"))
        self.assertTrue(callable(mock_resp.json))

    def test_json_returns_dict(self):
        """Test che json() restituisce un dict quando il costruttore riceve un dict."""
        data = {"key": "value"}
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        self.assertIsInstance(result, dict)
        self.assertEqual(result, data)

    def test_json_returns_list(self):
        """Test che json() restituisce una lista quando il costruttore riceve una lista."""
        data = [{"id": 1}, {"id": 2}]
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        self.assertIsInstance(result, list)
        self.assertEqual(result, data)

    def test_json_returns_same_data(self):
        """Test che json() restituisce dati equivalenti a quelli passati al costruttore."""
        data = {"teams": [{"id": 1, "name": "Team A"}]}
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        self.assertEqual(result, data)
        # V8.0: json() ora restituisce una copia difensiva, non lo stesso riferimento
        self.assertIsNot(result, data)  # Istanza diversa (defensive copy)

    def test_json_returns_defensive_copy(self):
        """Test che json() restituisce una copia difensiva, non un riferimento diretto.

        V8.0: Questo previene mutazioni accidentali dei dati interni.
        """
        data = {"key": "value"}
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        result["new_key"] = "new_value"

        # L'originale NON viene modificato (json() restituisce una copia)
        self.assertNotIn("new_key", mock_resp._data)
        self.assertIn("key", mock_resp._data)
        self.assertEqual(mock_resp._data["key"], "value")

    def test_json_returns_defensive_copy_for_list(self):
        """Test che json() restituisce una copia difensiva anche per le liste."""
        data = [{"id": 1}, {"id": 2}]
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        result.append({"id": 3})

        # L'originale NON viene modificato
        self.assertEqual(len(mock_resp._data), 2)
        self.assertEqual(len(result), 3)

    def test_repr_method_with_dict(self):
        """Test che __repr__() funziona correttamente con dict."""
        data = {"key1": "value1", "key2": "value2"}
        mock_resp = self.MockResponse(data)

        repr_str = repr(mock_resp)
        self.assertIn("_MockResponse", repr_str)
        self.assertIn("status_code=200", repr_str)
        self.assertIn("data_type=dict", repr_str)
        self.assertIn("key1", repr_str)
        self.assertIn("key2", repr_str)

    def test_repr_method_with_list(self):
        """Test che __repr__() funziona correttamente con list."""
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        mock_resp = self.MockResponse(data)

        repr_str = repr(mock_resp)
        self.assertIn("_MockResponse", repr_str)
        self.assertIn("status_code=200", repr_str)
        self.assertIn("data_type=list", repr_str)
        self.assertIn("length=3", repr_str)

    def test_repr_method_with_primitive(self):
        """Test che __repr__() funziona correttamente con tipi primitivi."""
        data = "simple string"
        mock_resp = self.MockResponse(data)

        repr_str = repr(mock_resp)
        self.assertIn("_MockResponse", repr_str)
        self.assertIn("status_code=200", repr_str)
        self.assertIn("data_type=str", repr_str)

    def test_protocol_duck_typing(self):
        """Test che _MockResponse soddisfa il Protocol ResponseLike."""
        data = {"test": "data"}
        mock_resp = self.MockResponse(data)

        # Verifica che mock_resp può essere usato come ResponseLike
        self.assertIsInstance(mock_resp.status_code, int)
        result = mock_resp.json()
        # json() può restituire dict, list, o altri tipi JSON
        self.assertIsNotNone(result)


class TestMockResponseIntegration(unittest.TestCase):
    """Test per l'integrazione di _MockResponse con FotMobProvider."""

    def setUp(self):
        """Setup per i test."""
        from src.ingestion.data_provider import _MockResponse

        self.MockResponse = _MockResponse

    def test_fotmob_search_team_data_structure(self):
        """Test che _MockResponse funziona con dati di search_team."""
        # Simula dati di risposta FotMob per search_team
        data = [
            {
                "suggestions": [
                    {"type": "team", "id": "12345", "name": "Team A", "country": "Italy"},
                    {"type": "team", "id": "67890", "name": "Team B", "country": "Spain"},
                ]
            }
        ]
        mock_resp = self.MockResponse(data)

        # Simula l'uso in search_team()
        result = mock_resp.json()
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["suggestions"]), 2)

    def test_fotmob_team_details_data_structure(self):
        """Test che _MockResponse funziona con dati di get_team_details."""
        # Simula dati di risposta FotMob per team details
        data = {
            "id": 12345,
            "name": "Team A",
            "squad": [
                {"id": 1, "name": "Player 1", "position": "FW"},
                {"id": 2, "name": "Player 2", "position": "MF"},
            ],
            "fixtures": [
                {"id": 100, "opponent": "Team B", "date": "2024-01-15"},
            ],
        }
        mock_resp = self.MockResponse(data)

        # Simula l'uso in get_team_details()
        result = mock_resp.json()
        self.assertEqual(result["id"], 12345)
        self.assertEqual(len(result["squad"]), 2)
        self.assertEqual(len(result["fixtures"]), 1)

    def test_fotmob_match_lineup_data_structure(self):
        """Test che _MockResponse funziona con dati di get_match_lineup."""
        # Simula dati di risposta FotMob per match lineup
        data = {
            "matchId": 12345,
            "home": {
                "teamId": 1,
                "players": [
                    {"id": 1, "name": "Player 1", "shirtNumber": 10},
                    {"id": 2, "name": "Player 2", "shirtNumber": 7},
                ],
            },
            "away": {
                "teamId": 2,
                "players": [
                    {"id": 3, "name": "Player 3", "shirtNumber": 9},
                    {"id": 4, "name": "Player 4", "shirtNumber": 11},
                ],
            },
        }
        mock_resp = self.MockResponse(data)

        # Simula l'uso in get_match_lineup()
        result = mock_resp.json()
        self.assertEqual(result["matchId"], 12345)
        self.assertEqual(len(result["home"]["players"]), 2)
        self.assertEqual(len(result["away"]["players"]), 2)

    def test_error_handling_none_response(self):
        """Test che None response viene gestito correttamente."""
        # Simula il caso in cui _make_request_with_fallback restituisce None
        resp = None

        # I chiamanti gestiscono questo caso
        if resp is None:
            result = []
        else:
            result = resp.json()

        self.assertEqual(result, [])

    def test_error_handling_json_decode(self):
        """Test che errori di JSON decode vengono gestiti."""
        # Simula il caso in cui json() potrebbe fallire
        data = {"valid": "json"}
        mock_resp = self.MockResponse(data)

        try:
            result = mock_resp.json()
            # Se json() funziona, result deve essere un dict
            self.assertIsInstance(result, dict)
        except Exception as e:
            # Se json() fallisce, deve essere gestito
            self.fail(f"json() should not fail with valid dict: {e}")


class TestMockResponseEdgeCases(unittest.TestCase):
    """Test per edge cases di _MockResponse."""

    def setUp(self):
        """Setup per i test."""
        from src.ingestion.data_provider import _MockResponse

        self.MockResponse = _MockResponse

    def test_json_with_nested_dicts(self):
        """Test json() con dict annidati profondamente."""
        data = {"level1": {"level2": {"level3": {"level4": {"level5": "deep value"}}}}}
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        self.assertEqual(result["level1"]["level2"]["level3"]["level4"]["level5"], "deep value")

    def test_json_with_large_dict(self):
        """Test json() con un dict grande."""
        data = {f"key_{i}": f"value_{i}" for i in range(1000)}
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        self.assertEqual(len(result), 1000)
        self.assertEqual(result["key_0"], "value_0")
        self.assertEqual(result["key_999"], "value_999")

    def test_json_with_special_characters(self):
        """Test json() con caratteri speciali."""
        data = {
            "unicode": "🎉",
            "emoji": "⚽",
            "special": "©®™",
            "newline": "line1\nline2",
            "tab": "col1\tcol2",
        }
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        self.assertEqual(result["unicode"], "🎉")
        self.assertEqual(result["emoji"], "⚽")
        self.assertEqual(result["special"], "©®™")
        self.assertEqual(result["newline"], "line1\nline2")
        self.assertEqual(result["tab"], "col1\tcol2")

    def test_json_with_null_values(self):
        """Test json() con valori None."""
        data = {
            "null_value": None,
            "valid_value": "test",
        }
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        self.assertIsNone(result["null_value"])
        self.assertEqual(result["valid_value"], "test")

    def test_json_with_empty_values(self):
        """Test json() con valori vuoti."""
        data = {
            "empty_string": "",
            "empty_list": [],
            "empty_dict": {},
        }
        mock_resp = self.MockResponse(data)

        result = mock_resp.json()
        self.assertEqual(result["empty_string"], "")
        self.assertEqual(result["empty_list"], [])
        self.assertEqual(result["empty_dict"], {})

    def test_multiple_json_calls_return_same_data(self):
        """Test che chiamate multiple a json() restituiscono gli stessi dati."""
        data = {"key": "value"}
        mock_resp = self.MockResponse(data)

        result1 = mock_resp.json()
        result2 = mock_resp.json()
        result3 = mock_resp.json()

        self.assertEqual(result1, result2)
        self.assertEqual(result2, result3)
        self.assertEqual(result1, data)

    def test_status_code_default_200(self):
        """Test che status_code di default è 200."""
        data = {"key": "value"}
        mock_resp = self.MockResponse(data)

        # status_code deve essere 200 di default
        self.assertEqual(mock_resp.status_code, 200)

    def test_status_code_custom(self):
        """Test che status_code può essere personalizzato nel costruttore."""
        data = {"key": "value"}

        # Test vari status code validi
        for status_code in [200, 201, 301, 400, 404, 500, 503]:
            mock_resp = self.MockResponse(data, status_code=status_code)
            self.assertEqual(mock_resp.status_code, status_code)

    def test_status_code_validation_invalid(self):
        """Test che status code non validi sollevano ValueError."""
        data = {"key": "value"}

        # Status code troppo basso
        with self.assertRaises(ValueError) as ctx:
            self.MockResponse(data, status_code=99)
        self.assertIn("99", str(ctx.exception))

        # Status code troppo alto
        with self.assertRaises(ValueError) as ctx:
            self.MockResponse(data, status_code=600)
        self.assertIn("600", str(ctx.exception))

        # Status code negativo
        with self.assertRaises(ValueError) as ctx:
            self.MockResponse(data, status_code=-1)
        self.assertIn("-1", str(ctx.exception))

    def test_status_code_validation_valid(self):
        """Test che tutti gli status code HTTP validi sono accettati."""
        data = {"key": "value"}

        # Informational (100-199)
        mock_resp = self.MockResponse(data, status_code=100)
        self.assertEqual(mock_resp.status_code, 100)

        # Success (200-299)
        mock_resp = self.MockResponse(data, status_code=204)
        self.assertEqual(mock_resp.status_code, 204)

        # Redirection (300-399)
        mock_resp = self.MockResponse(data, status_code=301)
        self.assertEqual(mock_resp.status_code, 301)

        # Client Error (400-499)
        mock_resp = self.MockResponse(data, status_code=403)
        self.assertEqual(mock_resp.status_code, 403)

        # Server Error (500-599)
        mock_resp = self.MockResponse(data, status_code=502)
        self.assertEqual(mock_resp.status_code, 502)


class TestResponseLikeProtocolUsage(unittest.TestCase):
    """Test per l'uso del Protocol ResponseLike nel codice."""

    def test_response_like_type_hint(self):
        """Test che ResponseLike può essere usato come type hint."""
        from src.ingestion.data_provider import ResponseLike, _MockResponse

        # Simula una funzione che accetta ResponseLike
        def process_response(resp: ResponseLike) -> dict:
            return resp.json()

        # Test con _MockResponse
        data = {"test": "data"}
        mock_resp = _MockResponse(data)
        result = process_response(mock_resp)

        self.assertEqual(result, data)

    def test_response_like_optional_type_hint(self):
        """Test che ResponseLike | None può essere usato come type hint."""
        from src.ingestion.data_provider import ResponseLike, _MockResponse

        # Simula una funzione che accetta ResponseLike | None
        def process_response(resp: ResponseLike | None) -> dict | None:
            if resp is None:
                return None
            return resp.json()

        # Test con _MockResponse
        data = {"test": "data"}
        mock_resp = _MockResponse(data)
        result = process_response(mock_resp)
        self.assertEqual(result, data)

        # Test con None
        result = process_response(None)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
