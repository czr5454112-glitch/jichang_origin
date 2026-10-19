import faulthandler,json,pytest,sys
faulthandler.dump_traceback_later(15,repeat=True)
raise SystemExit(pytest.main(json.loads(sys.argv[1])))
