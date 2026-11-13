import copy
import json
import unittest
from pathlib import Path

from main import to_api_prompt

ROOT = Path(__file__).parent
GRAPH = json.loads((ROOT / "wan2_2_5b_t2v.json").read_text(encoding="utf-8"))


class WanWorkflowTests(unittest.TestCase):
    def test_text_to_video_omits_disabled_image_node(self):
        prompt = to_api_prompt(copy.deepcopy(GRAPH), "BETANIA positive prompt")
        self.assertNotIn("56", prompt)
        self.assertNotIn("start_image", prompt["55"]["inputs"])
        self.assertEqual(prompt["6"]["inputs"]["text"], "BETANIA positive prompt")
        self.assertIn("SaveVideo", [node["class_type"] for node in prompt.values()])

    def test_image_to_video_activates_reference_node(self):
        graph = copy.deepcopy(GRAPH)
        image_node = next(node for node in graph["nodes"] if node["type"] == "LoadImage")
        image_node["mode"] = 0
        image_node["widgets_values"][0] = "betania-reference.png"
        prompt = to_api_prompt(graph, "BETANIA positive prompt")
        self.assertEqual(prompt["56"]["inputs"]["image"], "betania-reference.png")
        self.assertEqual(prompt["55"]["inputs"]["start_image"], ["56", 0])


if __name__ == "__main__":
    unittest.main()
