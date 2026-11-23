"""Checks for the actual constrained live model API, distinct from the prescribed benchmark."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import comprehensive_readings as reading


SOURCE = "Investigators used random allocation to place vocal students into the intervention group or the comparison group."
CLAIMS = [
    {"field":"study_design","text":"Vocal students were allocated to one of two groups at random.","quote":SOURCE},
    {"field":"limitations","text":"The study lacked a comparison group for assessing the effects.","quote":SOURCE},
]


def model_with(value, finish="stop"):
    model=Mock()
    content=value if isinstance(value,str) else json.dumps(value)
    model.create_chat_completion.return_value={"choices":[{"message":{"content":content},"finish_reason":finish}]}
    return model


class KeyedVerifierTests(unittest.TestCase):
    def test_one_required_decision_for_each_of_one_to_six_claims(self):
        for n in range(1,7):
            spec=reading.decision_schema(n)
            self.assertFalse(spec["additionalProperties"])
            self.assertEqual(spec["required"],[f"claim_{i}" for i in range(n)])
            for key in spec["required"]:
                self.assertEqual(set(spec["properties"][key]["enum"]),{"supported","rejected","insufficient"})
            self.assertEqual(reading.checked_decisions(dict.fromkeys(spec["required"],"supported"),n),
                             {"supported":list(range(n)),"rejected":[]})

    def test_actual_call_checks_the_false_no_control_claim_independently_and_holds_it(self):
        for status in ("rejected","insufficient"):
            model=model_with({"claim_0":"supported","claim_1":status})
            with self.assertRaisesRegex(ValueError,"claim_verification_failed"):
                reading.verify_source_claims(model,CLAIMS,SOURCE)
            call=model.create_chat_completion.call_args.kwargs
            self.assertEqual(call["response_format"]["schema"],reading.decision_schema(2))
            self.assertIn("one of two groups at random",call["messages"][-1]["content"])
            self.assertIn("lacked a comparison group",call["messages"][-1]["content"])
            self.assertEqual(model.create_chat_completion.call_count,1)

    def test_invalid_old_or_duplicated_output_never_grants_support(self):
        for answer in ({"claim_0":"supported"},{"claim_0":"supported","claim_1":"supported","claim_2":"supported"},
                       {"claim_0":"maybe","claim_1":"supported"},{"supported":[0,1],"rejected":[1]},
                       '{"claim_0":"rejected","claim_0":"supported","claim_1":"supported"}'):
            model=model_with(answer)
            with self.assertRaisesRegex(ValueError,"verifier_schema_invalid"):
                reading.verify_source_claims(model,CLAIMS,SOURCE)
            self.assertEqual(model.create_chat_completion.call_count,1)

    def test_truncated_all_positive_output_remains_a_hold(self):
        model=model_with({"claim_0":"supported","claim_1":"supported"},"length")
        with self.assertRaisesRegex(ValueError,"verifier_output_truncated"):
            reading.verify_source_claims(model,CLAIMS,SOURCE)

    def test_source_supported_singleton_closes_its_only_required_decision(self):
        self.assertEqual(reading.verify_source_claims(model_with({"claim_0":"supported"}),CLAIMS[:1],SOURCE),
                         {"supported":[0],"rejected":[]})
