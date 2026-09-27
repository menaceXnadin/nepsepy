"""Example: fetch public market data through the normal public-site flow.

Only calls endpoints the public website itself calls. Prints data summaries;
never prints token material.
"""

from nepsepy import NepseClient

PATH = "/api/nots/securityDailyTradeStat/58"


def main() -> None:
    with NepseClient() as client:
        client.bootstrap()
        print(client.describe_state())  # redacted
        data = client.get_json(PATH)
        if isinstance(data, list):
            print(f"rows: {len(data)}")
            for row in data[:5]:
                print(row.get("symbol"), row.get("lastTradedPrice"),
                      row.get("totalTradeQuantity"))
        else:
            print(type(data))


if __name__ == "__main__":
    main()
