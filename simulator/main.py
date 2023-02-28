import os

import modules.azure_data_explorer as ade
ade.test()

# instance_type = os.environ.get("INSTANCE_TYPE")
#
# if instance_type == "worker":
#     import worker
#     worker.run()
# else:
#     import collector
#     collector.run()
