import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tmh.platform import project_import as imp
from tmh.platform.errors import ApiError

class GitHubRetryTest(unittest.TestCase):
    def test_tls_reset_retries_clean_temporary_clone(self):
        with tempfile.TemporaryDirectory() as folder:
            tmp=Path(folder)/'clone';calls=[]
            def git(*a,**kw):
                calls.append(a)
                if len(calls)==1:
                    tmp.mkdir();(tmp/'partial').write_text('incomplete')
                    raise ApiError(500,'SSL_ERROR_SYSCALL')
                self.assertFalse(tmp.exists());tmp.mkdir();(tmp/'README').write_text('ok')
            with patch.object(imp,'_git',side_effect=git),patch.object(imp.time,'sleep'):
                self.assertEqual(imp._clone(None,None,{'url':'https://github.com/x/y.git'},tmp,'https://github.com/x/y.git')['files'],1)
            self.assertEqual(len(calls),2)
    def test_auth_errors_and_other_hosts_do_not_retry(self):
        for url,error in [('https://github.com/x/y.git','Authentication failed'),('https://example.org/x/y.git','SSL_ERROR_SYSCALL')]:
            with patch.object(imp,'_git',side_effect=ApiError(500,error)) as git, self.assertRaises(ApiError):
                imp._clone(None,None,{'url':url},Path('/unused'),url)
            self.assertEqual(git.call_count,1)
