def ok(data=None, message="ok"):
    return {"code": 0, "data": data, "message": message}

def fail(code=400, message="error"):
    return {"code": code, "data": None, "message": message}
