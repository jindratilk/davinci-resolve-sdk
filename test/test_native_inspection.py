import sys
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
import sdk_inspection_host as host
from cutagent_cli.adapters import ResolveTransport
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

if __name__=='__main__':unittest.main()
