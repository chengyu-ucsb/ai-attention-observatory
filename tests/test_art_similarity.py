"""Offline tests of coarse duplicate screening, not browser pixel fidelity."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import art_similarity as similarity


def svg(body='', viewbox='0 0 1200 760'):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="'+viewbox+'">'+body+'</svg>').encode()


def pixel(image,x,y,width=80):
    offset=(y*width+x)*3
    return tuple(image[offset:offset+3])


class CoarseRasterTests(unittest.TestCase):
    def test_empty_and_letterbox(self):
        self.assertEqual(similarity.rasterize(svg()),bytes(similarity.BACKGROUND)*4000)
        image=similarity.rasterize(svg('<rect width="100" height="100" fill="#000"/>','0 0 100 100'))
        self.assertEqual(pixel(image,0,25),similarity.BACKGROUND)
        self.assertEqual(pixel(image,40,25),(0,0,0))

    def test_fill_nonzero_hole_and_implicit_relative_commands(self):
        image=similarity.rasterize(svg('<path d="M10 10 h80 v80 h-80 z m20 20 v40 h40 v-40 z" fill="#E00122"/>','0 0 100 100'),100,100)
        self.assertEqual(pixel(image,15,15,100),(224,1,34))
        self.assertEqual(pixel(image,50,50,100),similarity.BACKGROUND)
        same=similarity.rasterize(svg('<path d="M10 10 90 10 90 90 10 90 Z" fill="#E00122"/>','0 0 100 100'),100,100)
        self.assertEqual(pixel(same,50,50,100),(224,1,34))

    def test_curves_rotation_and_opacity(self):
        image=similarity.rasterize(svg('<g transform="translate(50 50) rotate(90) scale(1)"><rect x="-30" y="-10" width="60" height="20" fill="#000000"/></g>','0 0 100 100'),100,100)
        self.assertEqual(pixel(image,50,25,100),(0,0,0))
        self.assertEqual(pixel(image,25,50,100),similarity.BACKGROUND)
        curved=similarity.rasterize(svg('<path d="M10 70 Q50 0 90 70 C70 90 30 90 10 70 Z" fill="#000" fill-opacity="0.5"/>','0 0 100 100'),100,100)
        self.assertEqual(pixel(curved,50,60,100),(122,120,116))
        self.assertEqual(pixel(curved,50,5,100),similarity.BACKGROUND)

    def test_stroke_dashes_and_rounded_rect(self):
        image=similarity.rasterize(svg('<path d="M10 50 H90" fill="none" stroke="#000" stroke-width="8" stroke-dasharray="10 10"/>','0 0 100 100'),100,100)
        self.assertEqual(pixel(image,15,50,100),(0,0,0))
        self.assertEqual(pixel(image,25,50,100),similarity.BACKGROUND)
        rounded=similarity.rasterize(svg('<rect x="10" y="10" width="80" height="80" rx="20" fill="#000"/>','0 0 100 100'),100,100)
        self.assertEqual(pixel(rounded,11,11,100),similarity.BACKGROUND)
        self.assertEqual(pixel(rounded,50,50,100),(0,0,0))

    def test_duplicate_tiny_changes_and_dominant_changes(self):
        body='<rect x="200" y="200" width="500" height="350" fill="#171714"/>'
        baseline=similarity.rasterize(svg(body))
        identical=similarity.compare(baseline,baseline)
        self.assertEqual(identical['full_mean_difference'],0.)
        self.assertEqual(identical['foreground_mean_difference'],0.)
        self.assertEqual(identical['foreground_iou'],1.)
        self.assertTrue(similarity.is_near_twin(identical))
        blank=similarity.rasterize(svg())
        self.assertFalse(similarity.is_near_twin(similarity.compare(blank,blank)))
        tiny=similarity.compare(baseline,similarity.rasterize(svg(body+'<circle cx="1000" cy="600" r="12" fill="#E00122"/>')))
        self.assertLess(tiny['full_mean_difference'],.025)
        self.assertLess(tiny['foreground_mean_difference'],.08)
        self.assertGreater(tiny['foreground_iou'],.84)
        self.assertTrue(similarity.is_near_twin(tiny))
        shifted=similarity.compare(baseline,similarity.rasterize(svg(body.replace('x="200"','x="205"'))))
        self.assertLess(shifted['foreground_mean_difference'],.08)
        moved=similarity.compare(baseline,similarity.rasterize(svg(body.replace('x="200"','x="650"'))))
        self.assertGreater(moved['foreground_mean_difference'],.4)
        self.assertLess(moved['foreground_iou'],.2)
        self.assertFalse(similarity.is_near_twin(moved))

    def test_foreground_metric_not_diluted_by_paper(self):
        a=bytes(similarity.PAPER)*1000+bytes((0,0,0))*10
        b=bytes(similarity.PAPER)*1000+bytes((224,1,34))*10
        result=similarity.compare(a,b)
        self.assertLess(result['full_mean_difference'],.01)
        self.assertGreater(result['foreground_mean_difference'],.3)

    def test_signature_roundtrip(self):
        image=similarity.rasterize(svg('<circle cx="600" cy="380" r="200" fill="#E00122"/>'))
        signature=similarity.encode_signature(image)
        self.assertEqual(similarity.decode_signature(signature),image)
        self.assertEqual(signature,similarity.encode_signature(image))
        for bad in ('bad', 'rgb1:!@#', 'rgb1:eA=='):
            with self.assertRaises(ValueError): similarity.decode_signature(bad)

    def test_unsupported_content_fails_explicitly(self):
        for body in ('<image href="other.svg"/>','<path d="M0 0 A1 1 0 0 0 9 9"/>',
                     '<rect width="100" height="100" filter="url(#f)"/>',
                     '<g transform="scale(1 2)"/>', '<path d="M1"/>',
                     '<path d="M0 0L50 50" fill="blue"/>',
                     '<path d="M0 0L50 50" style="fill:#000"/>'):
            with self.subTest(body=body),self.assertRaises(ValueError): similarity.rasterize(svg(body))
        with self.assertRaises(ValueError): similarity.rasterize(b'broken')
        with self.assertRaises(ValueError): similarity.rasterize(b'<!DOCTYPE svg><svg/>')
        with self.assertRaises(ValueError): similarity.compare(b'123',b'123456')

    def test_bounded_caches_and_mutable_result_isolation(self):
        similarity._rasterize_cached.cache_clear()
        similarity._compare_cached.cache_clear()
        content = svg('<circle cx="600" cy="380" r="200" fill="#E00122"/>')
        first = similarity.rasterize(content)
        self.assertEqual(first, similarity.rasterize(content))
        self.assertEqual(similarity._rasterize_cached.cache_info().hits, 1)
        self.assertEqual(similarity._rasterize_cached.cache_info().maxsize, 256)
        # Validation remains active even when a numerically equal key is cached.
        with self.assertRaises(ValueError):
            similarity.rasterize(content, width=80.0)
        other = similarity.rasterize(svg())
        original = similarity.compare(first, other)
        expected = dict(original)
        original['foreground_iou'] = -999
        original['extra'] = 'must not leak'
        self.assertEqual(similarity.compare(first, other), expected)
        self.assertEqual(similarity.compare(other, first), expected)
        self.assertEqual(similarity._compare_cached.cache_info().hits, 2)
        self.assertEqual(similarity._compare_cached.cache_info().maxsize, 8192)

    def test_actual_generated_fixture(self):
        import article_art
        titles = ('Cognitive offloading in doctoral academic writing',
                  'Clinical stress and insomnia',
                  'Governance and consent in university teaching')
        for title in titles:
            with self.subTest(title=title):
                record = {'title': title}
                inputs = article_art.public_inputs(record)
                spec = article_art.choose_concept(inputs)
                content = article_art.render_svg(
                    article_art.canonical_identity(record), inputs, spec)
                image = similarity.rasterize(content)
                self.assertEqual(len(image),12000)
                self.assertNotEqual(image,bytes(similarity.PAPER)*4000)
                self.assertEqual(image,similarity.rasterize(content))


if __name__ == '__main__': unittest.main()
