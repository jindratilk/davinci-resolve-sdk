import sys
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
import sdk_inspection_host as host
from cutagent_cli.adapters import ResolveTransport, EmbeddedFreeAdapter
from cutagent_cli.core.sdk_live_inspection import _required_mapping_call, _selected_media_identities
from cutagent_cli.errors import APICallFailed
from cutagent_cli.local_admission import verify_authorization_token

class Project:
    def GetName(self): return 'Source smoke'
    def GetUniqueId(self): return 'native-project-1'
    def GetTimelineCount(self): return 0
    def GetMediaPool(self): return None
    def GetCurrentTimeline(self): return None

class Manager:
    def __init__(self): self.reads=0
    def GetCurrentProject(self): self.reads+=1; return Project()
    def GetCurrentDatabase(self): return {'DbName':'Local disk','DbType':'Disk'}

class NativeInspectionTests(unittest.TestCase):
    def test_existing_inspector_brackets_native_project_without_commercial_auth(self):
        manager=Manager()
        adapter=SimpleNamespace(transport=ResolveTransport.STUDIO_EXTERNAL,
            connect=lambda:SimpleNamespace(GetProjectManager=lambda:manager))
        with patch.object(host,'select_adapter',return_value=adapter):
            result=host.inspect({'operation':'project.current','deadlineAtMs':int(time.time()*1000)+10000})
        self.assertEqual(result['before']['project']['project_id'],'native-project-1')
        self.assertEqual(result['before'],result['after'])
        self.assertGreaterEqual(manager.reads,2)
    def test_uncomposed_mutations_fail_before_native_connection(self):
        with patch.object(host,'select_adapter') as adapter:
            with self.assertRaises(ValueError):host.inspect({'operation':'marker.create'})
            adapter.assert_not_called()
        with self.assertRaises(PermissionError):verify_authorization_token('anything')
    def test_arbitrary_parameters_fail_before_native_connection(self):
        with patch.object(host,'select_adapter') as adapter:
            with self.assertRaises(ValueError):host.inspect({'operation':'project.current','script':'mutate()'})
            adapter.assert_not_called()

    def test_free_empty_metadata_tables_preserve_collection_shapes(self):
        adapter = EmbeddedFreeAdapter(client=SimpleNamespace(execute=lambda request: []))
        for method in ('GetMetadata', 'GetThirdPartyMetadata'):
            self.assertEqual(adapter.call('clip', method, []), {})
        self.assertEqual(adapter.call('folder', 'GetClipList', []), [])

    def test_selection_failure_is_not_reported_as_an_empty_selection(self):
        class MediaPool:
            def GetSelectedClips(self):
                raise RuntimeError('Free 21.1 does not provide this UI selection')

        with self.assertRaises(APICallFailed):
            _selected_media_identities(MediaPool(), None)

        class FalseMediaPool:
            def GetSelectedClips(self):
                return False

        self.assertEqual(_selected_media_identities(FalseMediaPool(), None), (set(), set()))

    def test_unreadable_metadata_is_not_reported_as_an_empty_mapping(self):
        for value in (False, None, [], ()):
            clip = SimpleNamespace(GetMetadata=lambda: value)
            with self.assertRaises(APICallFailed):
                _required_mapping_call(clip, 'GetMetadata')
        self.assertEqual(_required_mapping_call(SimpleNamespace(GetMetadata=lambda: {}), 'GetMetadata'), {})
        def failure():
            raise RuntimeError('transport failure')
        with self.assertRaises(APICallFailed):
            _required_mapping_call(SimpleNamespace(GetMetadata=failure), 'GetMetadata')

if __name__=='__main__':unittest.main()
