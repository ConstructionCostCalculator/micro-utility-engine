import os,tempfile,unittest
os.environ['DATABASE_PATH']=os.path.join(tempfile.gettempdir(),'solveease_'+str(os.getpid())+'.sqlite3')
import app
class TestSmoke(unittest.TestCase):
 def setUp(self):app.init_db();self.c=app.app.test_client()
 def test_health(self):self.assertEqual(self.c.get('/health').status_code,200)
if __name__=='__main__':unittest.main()
