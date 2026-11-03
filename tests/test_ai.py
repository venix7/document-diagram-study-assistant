import unittest
from types import SimpleNamespace

from backend.app.ai import AIService, source_list, validated_answer

PASSAGES = [
    SimpleNamespace(
        page_number=2, content="Binary search halves a sorted search interval."
    ),
    SimpleNamespace(
        page_number=7, content="Breadth-first search explores a graph by layers."
    ),
]


class GroundingTests(unittest.TestCase):
    def test_server_rejects_invalid_model_citations(self):
        self.assertEqual(source_list([3], PASSAGES), [])
        self.assertEqual(source_list([True], PASSAGES), [])
        result = validated_answer(
            {"answer": "An unsupported claim", "citations": [3]}, PASSAGES
        )
        self.assertEqual(result["citations"], [])
        self.assertIn("not contain enough", result["answer"])

    def test_citation_pages_come_from_database_passages(self):
        result = validated_answer(
            {"answer": "Binary search halves the interval.", "citations": [1, 1]},
            PASSAGES,
        )
        self.assertEqual(result["citations"][0]["page"], 2)
        self.assertEqual(len(result["citations"]), 1)

    def test_study_items_need_supported_answers(self):
        service = AIService.__new__(AIService)
        service.structured = lambda *args: {
            "items": [
                {
                    "question": "What is binary search?",
                    "answer": "Halving.",
                    "citations": [9],
                }
            ]
        }
        with self.assertRaises(ValueError):
            service.study_set("quiz", 1, PASSAGES)


if __name__ == "__main__":
    unittest.main()
