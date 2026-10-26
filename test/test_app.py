import os, tempfile, unittest
os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "solveease-test-" + str(os.getpid()) + ".sqlite3")
import app

class UtilityTests(unittest.TestCase):
    def setUp(self):
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()

    def test_clean_spacing_and_paragraphs(self):
        r = self.client.post("/api/clean", json={"text":"  Hello\t  world \r\n\r\n\r\n Next  "})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["cleaned_text"], "Hello world\n\nNext")

    def test_reject_non_string(self):
        self.assertEqual(self.client.post("/api/clean", json={"text":42}).status_code, 400)

    def test_health(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_admin_requires_secret(self):
        r = self.client.post("/api/admin/scan", headers={"X-Admin-Secret":"wrong"})
        self.assertEqual(r.status_code, 403)

    def test_root_renders(self):
        self.assertEqual(self.client.get("/").status_code, 200)

if __name__ == "__main__":
    unittest.main()
