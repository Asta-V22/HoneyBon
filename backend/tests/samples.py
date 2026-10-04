"""Real submissions used by the live review tests."""

from app.reviews.prompts import ReviewInput

# LeetCode 678 · Valid Parenthesis String. Accepted two-stack solution: O(n) time, O(n) space.
# The optimum is a greedy low/high open-count scan with O(1) space.
LC678_TWO_STACKS = ReviewInput(
    platform="leetcode",
    problem_title="Valid Parenthesis String",
    problem_slug="valid-parenthesis-string",
    problem_url="https://leetcode.com/problems/valid-parenthesis-string/",
    difficulty="Medium",
    statement=None,
    language="cpp",
    code="""class Solution {
public:
    bool checkValidString(string s) {
        stack<int> open;
        stack<int> star;

        for(int i=0; i<s.size(); i++){
            if(s[i]=='('){
                open.push(i);
            }
            else if(s[i]=='*'){
                star.push(i);
            }
            else{
                if(!open.empty()){
                    open.pop();
                }
                else{
                    if(!star.empty()){
                        star.pop();
                    }
                    else{
                        return false;
                    }
                }
            }
        }

        while(!open.empty()){
            int openidx = open.top();
            if(star.empty()) return false;
            int staridx = star.top();

            if(openidx<staridx){
                open.pop();
                star.pop();
            }
            else{
                return false;
            }
        }

        return true;
    }
};
""",
)
