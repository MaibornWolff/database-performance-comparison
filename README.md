# Database performance comparison for IoT use cases

MaibornWolff does a lot of IoT projects. One important part of IoT projects is storage and analysis of device data/events. To get some reliable numbers to help us choose well suited databases for specific use cases, we have started to compare some horizontally scalable databases in regards to how well they handle typical IoT workloads and tasks. We are doing this test for us but maybe it's of interest to other people as well. This repository contains the results and the tooling for this comparison.

Currently we only have one use case: Rapid and concurrent inserts to simulate data ingestion of device events (to keep it simple we simulate temperature events). Other use cases like different queries are planned but not yet implemented. The initial idea was to see how the scalable SQL databases YugabyteDB and CockroachDB perform in those use cases but since we were already at it we threw in ArangoDB in the mix and might add more databases like TimescaleDB later.

**This is a work-in-progress and is neither intended nor designed as a complete or standardized benchmark like TPC.**

This readme contains three sections:

1. The test results
2. How can the tests be replicated / how to use the test tooling
3. Short note on how you can make changes to the tests

## Benchmark

Using the test setup from this repository we ran tests against PostgreSQL, CockroachDB, YugabyteDB, ArangoDB and Cassandra with (aside from PostgreSQL) 3 nodes and 16 parallel workers that insert data (more concurrent workers might speed up the process but we didn't test that as this test was only to establish a baseline). All tests were done on a k3s cluster consisting of 8 m5ad.2xlarge (8vCPU, 32GB memory) and 3 i3.8xlarge (32vCPU, 244GB memory) EC2 instances on AWS. The database pods were run on the i3 instances with a resource limit of 8 cores and 10 GB memory per node, the client pods of the benchmark on the m5ad instances. In the text below all mentions of nodes refer to database nodes (pods) and not VMs or kubernetes nodes.

All tests were run on an empty database.

### Benchmark procedure

Upon execution the helm chart found in `deployment/` is installed on the cluster. By default we execute 3 runs and average out the results to compensate for fluctuations in performance. A run consists of the workers and one collector instance being spawned in individual pods inside the same k3s cluster. Due to node selectors workers could not run on the same nodes as DB instances to avoid interference.
Each worker generates and writes the configured amount of events into the database. Event schemata and API usage are found in `simulator/modules/{database_name}.py` (note: for cockroachdb and yugabytedb we use the postgres module), event generation logic may be reviewed under `simulator/modules/event_generator.py`.
After each run the workers reports statistics to the collector instance. The database is wiped inbetween separate runs to have a reproducible baseline.

For generating primary keys for the events we have two modes: Calculating it on the client side based on some of the fields that from a functional perspective guarantee uniqueness, or having the database increment a `SERIAL` primary key field. The exception here is Cassandra as using serial primary keys for rows opposes the main concepts of Cassandra we omitted this step and always relied on a db-generated unique partition key (device_id, timestamp).

For the insert testcase we use single inserts (for PostgreSQL with autocommit) to simulate an ingest where each message needs to be persisted as soon as possible so no batching of messages is possible. Depending on the architecture and implementation buffering and batching of messages is possible. To see what effect this has on the performance we have implemented a batch mode for the test.
For ArangoDB batch mode is implemented using the document batch API (`/_api/document`), the older generic batch API (`/_api/batch`) will be deprecated and produces worse performance so we did not use it. For PostgreSQL we implemented batch mode by doing a manual commit every x inserts and using COPY instead of INSERT. Another way to implement batch inserts is to use values lists (one insert statement with a list of values tuples) but this is not as fast as COPY. This mode can however be activated by passing `--extra-option use_values_lists=true`. 

### Insert performance

The table below shows the best results for the databases for a 3 node cluster (PostgreSQL being the exception having only a single instance) and a resource limit of 8 cores and 10 GB memory per node. All tests were done with a db-generated primary key except for CockroachDB for which we used a client-generated key.

| Database                                    | Inserts/s  | Insert mode                               |
|---------------------------------------------|------------|-------------------------------------------|
| PostgreSQL                                  | 215000     | values lists, size 1000                   |
| CockroachDB                                 |  14900     | values lists, size 1000                   |
| YugabyteDB YSQL                             |  19600     | values lists, size 1000                   |
| YugabyteDB YCQL                             | 250000     | batch mode, size 1000                   |
| ArrangoDB                                   | 137000     | batch mode, size 1000                     |
| Cassandra sync inserts                      | 389000     | batch mode, size 1000, max_sync_calls 1   |
| Cassandra async inserts                     | 410000     | batch mode, size 1000, max_sync_calls 120 |

You can find additional results from older runs in [old-results.md](old-results.md) but be aware that comparing them with the current ones is not always possible due to different conditions during the runs.

For PostgreSQL using batch mode increases the performance dramatically. With a batch size of 100 (so 100 inserts are accumulated until a commit is done) we achieved about 44000 inserts/s. Increasing the batch size further does not significantly improve performance. By using values lists performance can be increased even more.

When testing CockroachDB we sometimes ran into problems where transactions would error out with `TransactionAbortedError(ABORT_REASON_NEW_LEASE_PREVENTS_TXN)`. This slowed down testing and performance as we had to do retries to compensate.

For Yugabyte using YCQL instead of YSQL leverages enormous speed gains. But it comes at the cost of YCQL being less powerfull than YSQL in terms of queries. This needs to be balanced for each usecase individually to decide if all targeted queries can be done using YCQL or if YSQL really is needed.

The design of the primary key can have a huge impact on performance. For YugabyteDB speed drops to about one third when using a `SERIAL` primary key regardless of single or multi node instances. This indicates that the implementation of that algorithm suffers from the multi node synchronization and has no shortcut for single node clusters. CockroachDB shows a speed drop of about 10% so it is measureable but not as extreme. PostgreSQL has no measureable change. The same is true for ArangoDB.

ArangoDB achieves much of its speed by doing asynchronous writes as a normal insert will return before the document has been fsynced to disk. Enforcing that via `waitForSync` will massively slow down performance from 4500 insert/s to about 1500 for a 3 node cluster. For a single node instance it is even more pronounced with 7000 vs 1000 inserts/s. As long as ArangoDB is run in cluster mode enforcing sync should not be needed as replication ensures no data is lost if a single node goes down. So for our multi-node test we did not enforce sync.

For Cassandra we implemented two modes. One where after each insert the client waits for confirmation from the coordinator that the write was processed (called sync inserts in the table) and one where the clients sends several requests asynchronously. The limit of how many requests can be in-flight can be configured using the `max_sync_calls` parameter.
Although the results of our benchmarks show a drastic improvement, batching in most cases is not a recommended way to improve performance when using Cassandra. The current results are based on a singular device_id (and thus partition key) per worker. This results in all batched messages being processed as one write operation. With multiple devices per batch statement load on the coordinator node would increase and lead to performance and ultimately stability issues. (See [datastax docs on batching](https://docs.datastax.com/en/cql-oss/3.3/cql/cql_using/useBatch.html)).

## Running the tests

### Requirements

* A kubernetes cluster (tested with k3s 1.19.3 and minikube, any other should also work)
* Locally installed:
  * Python >= 3.8
  * kubectl
  * helm >= 3.4
  * Only tested on Linux, should also work on Mac, on Windows probably only with WSL

### Install database

You need a database to run the test against. To get you up and running quickly you can find below snippets to install databases using helm. Depending on what setup you want to test you need to edit the values files in `dbinstall/` to create a single or multi-node cluster. Depending on your cluster size and target workload you should also adapt the resource settings for each cluster.

Note: The provided values are for a k3s cluster. If you use another distribution or a cloud setup (e.g. EKS, AKS, GKE) please adapt them accordingly (at the minimum `storageClass`).

### Prepare the test

* Install the needed python dependencies: `pip install -r requirements.txt`
* If you use your own database installation or changed the provided ones edit `config.yaml`
  * Under `targets` edit the options for your database
  * if you want to use another kubernetes namespace than `default` set it there
* Make sure your local kubectl is configured and points to your cluster (Note: the `KUBECONFIG` environment override will currently not work correctly)

### Run the test

To run the test use `python run.py`. You can use the following options:

* `--target`: The target database to use (name must correspond to the target name in `config.yaml`). This is required
* `--workers`: Set of worker counts to try, default is `1,4,8,12,16` meaning the test will try with 1 concurrent worker, then with 4, then 8, then 12 and finally 16
* `--runs`: How often should the test be repeated for each worker count, default is `3`.
* `--primary-key`: Depending on the database using auto-generated primary keys (e.g. using the `SERIAL` type) can slow down the insert rate. Setting this to `db` means the database generates the primary key with the SERIAL datatype for compatibility with old PostgreSQL versions. Setting it to `sql` uses the standard GENERATED ALWAYS ... AS IDENTITY with a sequence cache size equal to the batch size, setting it to `client` means the workers supply a `varchar` primary key that is calculated based on the message content
* `--primary-key-constraint`: By default the primary key is declared as `PRIMARY KEY (id)`. This option can replace it, for example to use the natural key `PRIMARY KEY (device_id, timestamp, sequence_number)` or even define the sharding like `PRIMARY KEY (device_id hash, timestamp asc, sequence_number asc)` for YugabyteDB
* `--tables`: To simulate how the databases behave if inserts are done to several tables this option can be changed from `single` to `multiple` to have the test write into four instead of just one table
* `--num-inserts`: The number of inserts each worker should do, by default 10000 to get a quick result. Increase this to see how the databases behave under constant load. Also increase the timout option accordingly
* `--timeout`: How long should the script wait for the insert test to complete in seconds. Default is `0`. Increase accordingly if you increase the number of inserts or disable by stting to `0`
* `--batch`: Switch to batch mode (for postgres this means manual commits, for arangodb using the [batch api](https://docs.python-arango.com/en/main/batch.html)). Specify the number of inserts per transaction/batch
* `--extra-option`: Extra options to supply to the test scripts, can be used multiple times. Currently only used for ArangoDB (see below)
* `--clean` / `--no-clean`: By default the simulator will clean and recreate tables to always have the same basis for the runs. Can be disabled
* `--prefill`: Setting this to a positive number will insert that number of events into the database before starting the run
* `--steps`: Test performance with increasing database fill levels. Specifies the number of steps to do

If the test takes too long and the timeout is reached or the script runs into any problems it will crash. To clean up you must then manually uninstall the simulator by running `helm uninstall dbtest`.

### Prefill

By default the simulator will clean and recreate tables to always have the same basis for the runs. But in reality it is interesting to see how databases behave if they already have existing data. This can be accomplished in two ways:

* Manually prepare data and then tell the simulator to not clean up the existing data via `--no-clean`. You can also use this way to gradually fill up the database by not cleaning between runs.
* Use the `--prefill` option to have the simulator insert some data before doing the timed insert test. Independent of the chosen options the prefill will always happen in batch mode to be as fast as possible.

### Fill level performance

By default the simulator will test performance on an empty table. But it is also interesting to see how insert performance changes when the database already has existing data. To test that usecase you can use the `--steps <n>` option. The simulator will do the insert test `n` times without cleaning the tables between tests thereby testing the insert performance on existing data. The following constraints apply: The worker set can only contain one worker count and the run count must be `1`.

Example run with PostgreSQL:

```bash
python run.py --target postgresql -w 16 -r 1 --num-inserts 3125000 --batch 1000 --steps 10 --extra-option use_values_lists=true
Stepsize: 50000000
    Level Inserts/s
        0 182620
 50000000 181920
100000000 181150
150000000 181480
200000000 181920
250000000 182480
300000000 183660
350000000 181600
400000000 181200
450000000 182130
```

Each run will insert `num-inserts * workers` events (in this example 50 million) and the simulator will print a table with the number of existing events (fill level) and the insert performance for the next step.

Note that the results will have some spread depending on the environment and database. In normal tests this is compensated by doing several runs and averaging the results. For the fill level test this is not possible so treat the results accordingly.

## Database specifics

### PostgreSQL

PostgreSQL is our baseline as the representitive of the classic SQL databases.

For the test we installed postgres using:

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgres bitnami/postgresql -f dbinstall/postgresql-values.yaml
```

No other configuration / tuning was done.

### CockroachDB

CockroachDB is one of the representitives for distributed and scalable SQL databases with a postgres-compatible interface.

For the test we installed cockroachdb using:

```bash
helm repo add cockroachdb https://charts.cockroachdb.com/
helm install cockroachdb cockroachdb/cockroachdb -f dbinstall/cockroachdb-values.yaml
```

The values file as it is commited in git installs a 3 node cluster. To install a single node cluster change `statefulset.replicas` option and uncomment the `conf.single-node` option.

### YugabyteDB

YugabyteDB is one of the representitives for distributed and scalable SQL databases with a postgres-compatible interface.

For the test we installed yugabyteDB using:

```bash
helm repo add yugabytedb https://charts.yugabyte.com
helm install yugabyte yugabytedb/yugabyte -f dbinstall/yugabyte-values.yaml
```

The values file installs a 3 node cluster. To install a single node cluster change the `replicas` options. If you want more than 3 nodes you should set the `replicas.master` value to 3 and the `replicas.tserver` value to the node count you desire.

### ArangoDB

ArangoDB represents document databases without a fixed schema.

For the test we installed arangodb using:

```bash
export OPERATOR_VERSION=1.1.5
export URLPREFIX=https://github.com/arangodb/kube-arangodb/releases/download/${OPERATOR_VERSION}
helm install kube-arangodb $URLPREFIX/kube-arangodb-crd-${OPERATOR_VERSION}.tgz
helm install kube-arangodb-crd $URLPREFIX/kube-arangodb-${OPERATOR_VERSION}.tgz
kubectl apply -f dbinstall/arangodb-deployment.yaml
```

The values file installs a single node cluster. To install a 3 node cluster change `spec.mode` to `Cluster` and comment in the `spec.dbservers` options.

As a speciality for ArangoDB you can/must set extra options when running the test:

* `replication_factor`: By default this is set to `1`, to produce behaviour similar to the other databases in a cluster setting set this to `3`
* `shard_count`: By setting this option the collection will be created with the specified number of shards
* `sync`: By default the workers will not use the `waitForSync` option. Set this to `true` to force durable writes

### Cassandra

For Cassandra we rely on the k8ssandra project to install clusters on kubernetes.

```bash
helm repo add k8ssandra https://helm.k8ssandra.io/stable
helm install k8ssandra k8ssandra/k8ssandra -f dbinstall/k8ssandra-values.yaml
```

Note: In some tests we ran into timeouts during inserts. To compensate we edited the CassandraDatacenter resource after installation and added `write_request_timeout_in_ms: 10000` to the cassandra config.

For Cassandra the special parameter `max_sync_calls` can be specified. Setting it to `1` will have the client behave in a synchronous manner, waiting for the coordinator to confirm the insert before sending the next. Setting it to a value greater than one will have the client keep that many insert requests in flight and only blocking when the number is reached.

## Developing

This tool is split into two parts:

* A simulator that runs in kubernetes and does the work. It is split into a collector pod that initializes the database tables and collects the results and worker pods that run the workload (currently inserts).
* A cli that repeatedly launches the simulator with differnet arguments, collects the results and provides them to the user.

If you want to change the simulator you need to build your own docker image. The dockerfile for that is in the `simulator` folder. Afterwards change the `image.name` and `image.tag` parameters in the `deployment/values.yaml` file.
