Point implements interfaces to telescope mounts. It currently supports two mount types: Celestron NexStar and Losmandy Gemini 2. This package requires Python 3 (3.6 or newer). Python 2 is not supported.

Class `NexStar` wraps the serial commands supported by the Celestron NexStar telescope hand controllers. All of the commands in [this document](http://www.nexstarsite.com/download/manuals/NexStarCommunicationProtocolV1.2.zip) are supported. See the comments in the source code for information on each function. This project has been tested by the author with a Celestron NexStar 130 SLT.

Class `Gemini2` wraps the serial commands for the Gemini 2 mount computer. Both the serial and UDP protocol interfaces to Gemini 2 are supported. The command set is documented [here](http://www.gemini-2.com/web/L5V2_1serial.html) and the UDP protocol is documented [here](http://gemini-2.com/Gemini2_drivers/UPD_Protocol/Gemini_UDP_Protocol_Specification_1.2.pdf).
