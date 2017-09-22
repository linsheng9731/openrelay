import argparse
import logging
import json

import redis
import dynamo
import order
import util

logger = logging.getLogger(__name__)

def record_order(data, locker):
    order_obj = order.Order.FromBytes(data)
    # Make sure that only one process at a time is updating a given order
    with locker.lock(order_obj.orderHash):
        try:
            dynamo_order = dynamo.DynamoOrder.get(order_obj.orderHash)
        except dynamo.DynamoOrder.DoesNotExist:
            dynamo_order = dynamo.DynamoOrder.FromOrder(order_obj)
        # If the incoming record shows a higher makerTokenFilledAmount than
        # we've previously stored, update it
        stored_filled = util.bytesToInt(dynamo_order.makerTokenAmountFilled)
        if order_obj.makerTokenAmountFilled > stored_filled:
            incoming_filled = util.intToBytes(order_obj.makerTokenAmountFilled)
            dynamo_order.makerTokenAmountFilled = incoming_filled
        dynamo_order.save()


# def record_fill(orderHash, filled_amount, locker):
#     return dynamo.DynamoOrder.addFilled(orderHash, filled_amount, locker)


def get_redis_client(redis_url):
    try:
        host, port = redis_url.split(":")
    except ValueError:
        host = redis_url
        port = 6379
    return redis.StrictRedis(host=host, port=int(port), db=0)


def index_orders(redis_url, order_queue):
    redisClient = get_redis_client(redis_url)
    while True:
        with util.get_queue_message(order_queue, redisClient) as message:
            try:
                record_order(message, redisClient)
            except Exception:
                logger.exception("Error recording message")

# def fill_monitor():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("redis_url")
#     parser.add_argument("fill_queue")
#     args = parser.parse_args
#
#     redisClient = get_redis_client(args.redis_url)
#
#     while True:
#         with util.get_queue_message(args.fill_queue, redisClient) as message:
#             fill = json.loads(message.decode("utf8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("redis_url")
    parser.add_argument("order_queue")
    parser.add_argument("--create", action="store_true", default=False)
    args = parser.parse_args()
    if args.create and not dynamo.DynamoOrder.exists():
        dynamo.DynamoOrder.create_table(wait=True)
    index_orders(args.redis_url, args.order_queue)