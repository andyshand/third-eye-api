

next_generation_id = 0


class Generation(object):
    def __init__(self, prompt, model, sub_model, args):
        self.model = model
        self.prompt = prompt
        self.args = args
        self.submodel = sub_model
        self.id = ++next_generation_id

    def set_status(self, status):
        self.status = status;

    def done(self, result_image):
        self.result_image = result_image
        self.percentage = 100

    def set_progress(self, percentage, time_so_far, time_left):
        self.percentage = percentage
        self.time_so_far = time_so_far
        self.time_left = time_left

    def save_progress_image(self, image, path):
        image.save(path)
        self.progress_image = path
