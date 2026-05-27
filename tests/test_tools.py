import pytest
from execution.tools.builtins.http import http_request
from execution.tools.builtins.fileio import file_read, file_write
from execution.tools.builtins.image import image_process


class TestBuiltinTools:
    async def test_http_request_invalid_url(self):
        result = await http_request(url="http://nonexistent.invalid", timeout=2)
        assert "error" in result or "status_code" in result

    async def test_file_write_read(self, tmp_path):
        test_file = tmp_path / "test.txt"
        await file_write(str(test_file), "hello world")
        result = await file_read(str(test_file))
        assert result["content"] == "hello world"
        assert result["size"] == 11