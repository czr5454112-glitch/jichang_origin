package App;
public class Edge {
	int Star;
	int End;
	double length;
	double v;
	boolean fault = false;
	public int getStar() {
		return Star;
	}
	public void setStar(int star) {
		this.Star = star;
	}
	public int getEnd() {
		return End;
	}
	public void setEnd(int end) {
		this.End = end;
	}
	public double getLength() {
		return length;
	}
	public void setLength(double length) {
		this.length = length;
	}
	public double getV() {
		return v;
	}
	public void setV(double v) {
		this.v = v;
	}
	public boolean isFault() {
		return fault;
	}
	public void setFault(boolean fault) {
		this.fault = fault;
	}
}
