import copy,unittest
import test_compact_screen_transport as fixture
from compact_screen_transport import decode
from localize_native_decode import decode_articles

class LocalizedNativeContracts(unittest.TestCase):
    def test_valid_semantic_values_unchanged_and_bad_article_stays_unread(self):
        f=fixture.CompactTransportContracts();p=f.packet();r=f.answer()
        self.assertEqual((decode(p,r),[]),decode_articles(p,r,decode))
        second=copy.deepcopy(p['articles'][0]);second['id']='r20'
        for seg in second['paragraphs']:seg['id']=seg['id'].replace('r19:','r20:')
        p['articles'].append(second);p['expected_article_ids'].append('r20')
        r['items'][0]['g'][0]['q']=[copy.deepcopy(r['items'][0]['g'][0])]
        r['items'].append({'i':'r20','c':'z','g':[]})
        out,issues=decode_articles(p,r,decode)
        self.assertEqual({'id':'r20','code':'no_independent_analysis','views':[]},out['items'][1])
        self.assertEqual('invalid_compact_article',out['items'][0]['code']);self.assertEqual('r19',issues[0]['id'])
    def test_unknown_article_cannot_be_guessed_into_place(self):
        f=fixture.CompactTransportContracts();r=f.answer();r['items'][0]['i']='r999'
        with self.assertRaises(ValueError):decode_articles(f.packet(),r,decode)

if __name__=='__main__':unittest.main()
