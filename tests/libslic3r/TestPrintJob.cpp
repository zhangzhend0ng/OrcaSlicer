#include "catch2/catch.hpp"
#include "slic3r/App/PrintJobModel.hpp"

using namespace Slic3r;

TEST_CASE("PrintJob jobStateToString covers all states", "[PrintJob]") {
    REQUIRE(PrintJobModel::jobStateToString(PrintJobModel::JobState::Idle) == "Idle");
    REQUIRE(PrintJobModel::jobStateToString(PrintJobModel::JobState::Printing) == "Printing");
    REQUIRE(PrintJobModel::jobStateToString(PrintJobModel::JobState::Failed) == "Failed");
}

TEST_CASE("PrintJob isValidGCodePath", "[PrintJob]") {
    REQUIRE(PrintJobModel::isValidGCodePath("test.gcode"));
    REQUIRE(PrintJobModel::isValidGCodePath("test.gco"));
    REQUIRE_FALSE(PrintJobModel::isValidGCodePath("test.stl"));
    REQUIRE_FALSE(PrintJobModel::isValidGCodePath("short"));
}

TEST_CASE("PrintJob parseHostPort with port", "[PrintJob]") {
    std::string host;
    int port = 0;
    REQUIRE(PrintJobModel::parseHostPort("192.168.1.1:8080", host, port));
    REQUIRE(host == "192.168.1.1");
    REQUIRE(port == 8080);
}

TEST_CASE("PrintJob parseHostPort default port", "[PrintJob]") {
    std::string host;
    int port = 0;
    REQUIRE(PrintJobModel::parseHostPort("printer.local", host, port));
    REQUIRE(host == "printer.local");
    REQUIRE(port == 80);
}

TEST_CASE("PrintJob cancelJob guards", "[PrintJob][MVVP]") {
    PrintJobModel model;
    REQUIRE_FALSE(model.cancelJob.canExecute());
    model.jobState.set(PrintJobModel::JobState::Sending);
    REQUIRE(model.cancelJob.canExecute());
}
