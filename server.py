#!/usr/bin/env python3
import os
import tornado.ioloop
import tornado.web

class MainHandler(tornado.web.RequestHandler):
    def get(self, path):
        base_path="/mnt/data2/"
        fp = os.path.join(base_path, path)
        if not os.path.exists(fp):
            return self.write("Not found")
        if os.path.isdir(fp):
            items = os.listdir(fp)
            items2 = []
            for item in items:
                if os.path.isdir(os.path.join(fp,item)):
                    item = item+"/"
                items2.append(item)
            self.render("dir.html",items=items2, title=path)
            return
        self.set_header("Content-Type", "binary/octet-stream")
        self.write(open(fp,"rb").read())

application = tornado.web.Application([
    (r"/(.*)", MainHandler),
], debug=True)

if __name__ == "__main__":
    application.listen(1234)
    tornado.ioloop.IOLoop.instance().start()
