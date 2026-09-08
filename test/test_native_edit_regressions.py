"""Selected native regressions from accepted source f9152d5e1; simulated only."""
import sys,struct,unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
from cutagent_cli.core import edit_insert_overwrite as placement, edit_trim_db
from cutagent_cli.errors import ReadinessFailed
class NativeEditRegressions(unittest.TestCase):
 def test_fields_blob_packed_encodings_and_unknown_shapes(self):
  proto=b'\x0a\x0cFL::Retimer'
  for body in [b'\x80'+proto,b'\x81'+placement.zstd.ZstdCompressor(level=3).compress(proto)]:
   self.assertEqual(placement._fields_blob_names(struct.pack('>II',2,len(body))+body),{'FL::Retimer'})
  for blob in [b'unknown',struct.pack('>II',2,2)+b'\x80',struct.pack('>II',2,2)+b'\x82x']:
   with self.assertRaises(ReadinessFailed) as caught:placement._fields_blob_names(blob)
   self.assertEqual(caught.exception.details['reason'],'edge_db_state_undecodable')
 def test_native_inclusive_source_end_becomes_half_open(self):
  item=Mock()
  for name,value in {'GetName':'shot.mov','GetStart':0,'GetEnd':148,'GetUniqueId':'item-1','GetLeftOffset':30,'GetRightOffset':100,'GetSourceStartFrame':30,'GetSourceEndFrame':118}.items():getattr(item,name).return_value=value
  media=Mock();media.GetMediaId.return_value='media-1';media.GetClipProperty.return_value={'FPS':str(30000/1001),'Type':'Video'};item.GetMediaPoolItem.return_value=media
  row=edit_trim_db._live_row(item,track_type='video',track_index=1)
  self.assertEqual(row['source_end_frame_exclusive'],119)
  item.GetSourceEndFrame.return_value=None
  self.assertIsNone(edit_trim_db._live_row(item,track_type='video',track_index=1)['source_end_frame_exclusive'])
